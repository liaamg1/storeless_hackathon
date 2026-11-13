"""Presentation jobs and slide artifacts reuse files, processing_jobs and document_pages."""
from dataclasses import dataclass
from pathlib import Path
from psycopg.types.json import Jsonb

from app.core.database import get_connection
from app.processors.presentation_processor import ExtractedSlide
from app.schemas.presentation import PresentationRecord

_RECORD = """SELECT f.id AS file_id, f.filename, f.size_bytes, f.uploaded_at,
    f.storage_path, j.id AS job_id, COALESCE(j.status, 'not_processed') AS status,
    j.current_step, j.error_message,
    (SELECT count(*) FROM document_pages p WHERE p.file_id=f.id AND p.content_hash IS NOT NULL) AS slide_count
    FROM files f LEFT JOIN processing_jobs j ON j.file_id=f.id AND j.job_type='presentation_analysis'"""
_SUPPORTED = "lower(f.filename) ~ '\\.(pdf|pptx)$'"


@dataclass(frozen=True)
class PresentationJob:
    job_id: int
    file_id: int
    storage_path: Path
    kind: str


def get_source(file_id: int) -> dict | None:
    with get_connection() as connection:
        return connection.execute(_RECORD + ' WHERE f.id=%s AND ' + _SUPPORTED, (file_id,)).fetchone()


def list_presentations() -> list[PresentationRecord]:
    with get_connection() as connection:
        rows = connection.execute(_RECORD + ' WHERE ' + _SUPPORTED + ' ORDER BY f.id DESC').fetchall()
    return [PresentationRecord(**row) for row in rows]


def queue_existing(file_id: int) -> PresentationRecord:
    with get_connection() as connection:
        connection.execute(
            """INSERT INTO processing_jobs (file_id, job_type) VALUES (%s, 'presentation_analysis')
               ON CONFLICT (file_id, job_type) DO UPDATE SET status='queued', current_step='queued',
               error_message=NULL, started_at=NULL, completed_at=NULL
               WHERE processing_jobs.status='failed'""", (file_id,),
        )
    return PresentationRecord(**get_source(file_id))


def create_presentation(filename: str, size_bytes: int, sha256: str, path: Path, *, processing_options: list[str] | None = None) -> PresentationRecord:
    with get_connection() as connection:
        with connection.transaction():
            file = connection.execute(
                """INSERT INTO files (filename, size_bytes, sha256, storage_path, file_type, processing_options)
                   VALUES (%s,%s,%s,%s,%s,%s) RETURNING id, uploaded_at""",
                (filename, size_bytes, sha256, str(path), path.suffix[1:], Jsonb(processing_options) if processing_options is not None else None),
            ).fetchone()
            file_id = file['id']
            job = connection.execute("INSERT INTO processing_jobs (file_id, job_type) VALUES (%s,'presentation_analysis') RETURNING id", (file_id,)).fetchone()
    return PresentationRecord(file_id=file_id, filename=filename, size_bytes=size_bytes,
                              uploaded_at=file['uploaded_at'], job_id=job['id'], status='queued',
                              current_step='queued', error_message=None, slide_count=0)


def claim_presentation_job() -> PresentationJob | None:
    with get_connection() as connection:
        with connection.transaction():
            job = connection.execute(
                """SELECT j.id AS job_id, j.file_id, f.storage_path, f.filename FROM processing_jobs j
                   JOIN files f ON f.id=j.file_id WHERE j.job_type='presentation_analysis' AND j.status='queued'
                   ORDER BY j.id FOR UPDATE OF j SKIP LOCKED LIMIT 1""",
            ).fetchone()
            if job is None:
                return None
            connection.execute("UPDATE processing_jobs SET status='processing', current_step='rendering_slides', started_at=NOW(), error_message=NULL WHERE id=%s", (job['job_id'],))
    return PresentationJob(job['job_id'], job['file_id'], Path(job['storage_path']), Path(job['filename']).suffix.lower()[1:])


def complete_presentation(job: PresentationJob, slides: list[ExtractedSlide]) -> None:
    with get_connection() as connection:
        with connection.transaction():
            current = connection.execute('SELECT status FROM processing_jobs WHERE id=%s FOR UPDATE', (job.job_id,)).fetchone()
            if current is None or current['status'] != 'processing':
                raise ValueError('Presentation job is no longer processing.')
            with connection.cursor() as cursor:
                # Keep any existing PDF extraction text untouched. New PPTX pages
                # gain the same searchable text model as existing PDF documents.
                cursor.executemany(
                    """INSERT INTO document_pages (file_id,page_number,extracted_text,image_path,
                           thumbnail_path,content_hash,perceptual_hash,slide_processed_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,NOW())
                       ON CONFLICT (file_id,page_number) DO UPDATE SET image_path=EXCLUDED.image_path,
                           thumbnail_path=EXCLUDED.thumbnail_path,content_hash=EXCLUDED.content_hash,
                           perceptual_hash=EXCLUDED.perceptual_hash,slide_processed_at=NOW()""",
                    [(job.file_id, s.number, s.text, str(s.image_path), str(s.thumbnail_path), s.content_hash, s.perceptual_hash) for s in slides],
                )
            connection.execute("UPDATE processing_jobs SET status='completed',current_step='completed',error_message=NULL,completed_at=NOW() WHERE id=%s", (job.job_id,))


def get_analyzed_slides() -> list[dict]:
    """Read cached hashes once; never render or open originals during comparison."""
    with get_connection() as connection:
        return connection.execute(
            """SELECT p.id,p.file_id,f.filename,p.page_number AS slide_number,
                      p.extracted_text AS text,p.content_hash,p.perceptual_hash,
                      p.slide_processed_at AS processed_at
               FROM document_pages p JOIN files f ON f.id=p.file_id
               JOIN processing_jobs j ON j.file_id=f.id AND j.job_type='presentation_analysis'
               WHERE j.status='completed' AND p.content_hash IS NOT NULL
               ORDER BY p.file_id,p.page_number""",
        ).fetchall()


def get_slide_path(slide_id: int, thumbnail: bool) -> str | None:
    # The selected column is a server constant, never client SQL.
    column = 'thumbnail_path' if thumbnail else 'image_path'
    with get_connection() as connection:
        row = connection.execute(
            f"""SELECT p.{column} AS path FROM document_pages p JOIN processing_jobs j
                ON j.file_id=p.file_id AND j.job_type='presentation_analysis'
                WHERE p.id=%s AND j.status='completed'""", (slide_id,),
        ).fetchone()
    return row['path'] if row else None
