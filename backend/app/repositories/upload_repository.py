"""Persist selections on files and reuse the existing job queue and page records."""

from pathlib import Path
from collections.abc import Callable

from psycopg.types.json import Jsonb

from app.core.database import get_connection
from app.processors.pdf_processor import ExtractedPage


def snapshot(file_id: int) -> dict | None:
    with get_connection() as connection:
        file = connection.execute(
            """SELECT id,filename,size_bytes,storage_path,processing_options,uploaded_at,duplicate_of,original_removed_at,
                      EXISTS(SELECT 1 FROM document_pages p WHERE p.file_id=f.id) AS has_pages
               FROM files f WHERE id=%s""",
            (file_id,),
        ).fetchone()
        if file:
            file['jobs'] = connection.execute(
                'SELECT job_type,status,current_step,error_message,progress_current,progress_total,progress_unit FROM processing_jobs WHERE file_id=%s',
                (file_id,),
            ).fetchall()
    return file


def history_ids() -> list[int]:
    with get_connection() as connection:
        return [
            row['id']
            for row in connection.execute(
                'SELECT id FROM files WHERE processing_options IS NOT NULL AND original_removed_at IS NULL ORDER BY id DESC',
            ).fetchall()
        ]


def find_existing(digest: str, size: int, suffix: str) -> int | None:
    with get_connection() as connection:
        rows = connection.execute(
            '''SELECT f.id,f.filename,f.storage_path FROM files f
               LEFT JOIN processing_jobs speech ON speech.file_id=f.id AND speech.job_type='video_transcription'
               LEFT JOIN processing_jobs visual ON visual.file_id=f.id AND visual.job_type='video_visuals'
               WHERE lower(f.sha256)=%s AND f.size_bytes=%s AND f.original_removed_at IS NULL
               ORDER BY CASE WHEN speech.status='completed' THEN 0 WHEN speech.status IN ('queued','processing') THEN 1 ELSE 2 END,
                        CASE WHEN visual.status='completed' THEN 0 ELSE 1 END,f.id''',
            (digest, size),
        ).fetchall()
    for row in rows:
        if (
            Path(row['filename']).suffix.lower() == suffix
            and row['storage_path']
            and Path(row['storage_path']).is_file()
            and Path(row['storage_path']).stat().st_size == size
        ):
            return row['id']
    return None


def merge_options(file_id: int, operations: list[str]) -> None:
    with get_connection() as connection:
        with connection.transaction():
            file = connection.execute(
                'SELECT processing_options FROM files WHERE id=%s FOR UPDATE', (file_id,)
            ).fetchone()
            current = file['processing_options']
            if current is None:
                jobs = connection.execute(
                    'SELECT job_type,status FROM processing_jobs WHERE file_id=%s', (file_id,)
                ).fetchall()
                current = []
                names = {
                    'video_transcription': 'transcribe',
                    'video_visuals': 'visuals',
                    'presentation_analysis': 'slides',
                    'duplicate_check': 'duplicates',
                }
                current.extend(names[job['job_type']] for job in jobs if job['job_type'] in names)
                # Preserve visual work already authorized by a legacy recording upload.
                if any(
                    j['job_type'] == 'video_transcription' and j['status'] in ('queued', 'processing')
                    for j in jobs
                ):
                    current.append('visuals')
            connection.execute(
                'UPDATE files SET processing_options=%s WHERE id=%s',
                (Jsonb(sorted(set(current + operations))), file_id),
            )


def queue(file_id: int, job_type: str) -> bool:
    with get_connection() as connection:
        active = connection.execute(
            'SELECT id FROM files WHERE id=%s AND original_removed_at IS NULL FOR KEY SHARE', (file_id,)
        ).fetchone()
        if not active:
            raise ValueError('This original was removed; use its retained copy.')
        return bool(
            connection.execute(
                """INSERT INTO processing_jobs (file_id,job_type) VALUES (%s,%s)
               ON CONFLICT(file_id,job_type) DO UPDATE SET progress_current=NULL,progress_total=NULL,progress_unit=NULL,worker_slot=NULL,worker_id=NULL,status='queued',current_step='queued',
               error_message=NULL,started_at=NULL,completed_at=NULL WHERE processing_jobs.status='failed'
               RETURNING id""",
                (file_id, job_type),
            ).fetchone()
        )


def run_inline(file_id: int, job_type: str, action: Callable[[], object]) -> None:
    """Record real synchronous work; retry failed steps without uploading again."""
    queue(file_id, job_type)
    with get_connection() as connection:
        claimed = connection.execute(
            """UPDATE processing_jobs SET status='processing',current_step=%s,started_at=NOW()
               WHERE file_id=%s AND job_type=%s AND status='queued' RETURNING id""",
            (job_type, file_id, job_type),
        ).fetchone()
    if not claimed:
        return
    try:
        action()
        status, message = 'completed', None
    except Exception:
        status, message = (
            'failed',
            'This processing step failed. Retry processing this stored file; the original is preserved.',
        )
    with get_connection() as connection:
        connection.execute(
            'UPDATE processing_jobs SET status=%s,current_step=%s,error_message=%s,completed_at=NOW() WHERE id=%s',
            (status, status, message, claimed['id']),
        )


def add_pdf_pages(file_id: int, pages: list[ExtractedPage]) -> None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO document_pages(file_id,page_number,extracted_text) VALUES(%s,%s,%s)
                   ON CONFLICT(file_id,page_number) DO NOTHING""",
                [(file_id, page.page_number, page.text) for page in pages],
            )
