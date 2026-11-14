"""Atomic smallest-first claims, scoped recovery, and measurable phase progress."""

from dataclasses import dataclass
from pathlib import Path

from app.core.database import get_connection, new_connection
from app.core import worker_context

TYPES = {
    'transcription': ['video_transcription'],
    'document': ['pdf_text', 'presentation_analysis', 'duplicate_check'],
    'visual': ['video_visuals'],
}


@dataclass(frozen=True)
class Job:
    job_id: int
    file_id: int
    job_type: str
    storage_path: Path
    kind: str
    duration_ms: int | None


def claim(kind: str) -> Job | None:
    with get_connection() as connection:
        with connection.transaction():
            row = connection.execute(
                """
                SELECT j.id AS job_id,j.file_id,j.job_type,f.storage_path,f.filename,f.duration_ms
                FROM processing_jobs j JOIN files f ON f.id=j.file_id
                WHERE j.status='queued' AND j.job_type=ANY(%s) AND f.original_removed_at IS NULL
                AND (j.job_type<>'video_visuals' OR EXISTS (
                    SELECT 1 FROM processing_jobs s WHERE s.file_id=f.id
                    AND s.job_type='video_transcription' AND s.status='completed'))
                AND (j.job_type<>'presentation_analysis' OR NOT EXISTS (
                    SELECT 1 FROM processing_jobs p WHERE p.file_id=f.id
                    AND p.job_type='pdf_text' AND p.status<>'completed'))
                AND (j.job_type<>'video_transcription' OR NOT EXISTS (
                    SELECT 1 FROM files prior_file
                    JOIN processing_jobs prior_job ON prior_job.file_id=prior_file.id
                    WHERE prior_file.id<f.id AND prior_file.sha256=f.sha256
                    AND prior_file.size_bytes=f.size_bytes AND prior_file.original_removed_at IS NULL
                    AND prior_job.job_type='video_transcription'
                    AND prior_job.status IN ('queued','processing')))
                ORDER BY f.size_bytes ASC,j.created_at ASC,j.id ASC
                FOR UPDATE OF j SKIP LOCKED LIMIT 1
            """,
                (TYPES[kind],),
            ).fetchone()
            if row is None:
                return None
            steps = {
                'video_transcription': 'validating_video',
                'pdf_text': 'pdf_text',
                'presentation_analysis': 'rendering_slides',
                'video_visuals': 'extracting_visuals',
                'duplicate_check': 'duplicate_check',
            }
            connection.execute(
                """UPDATE processing_jobs SET status='processing',current_step=%s,
                worker_slot=%s,worker_id=%s,started_at=NOW(),completed_at=NULL,error_message=NULL,
                progress_current=NULL,progress_total=NULL,progress_unit=NULL WHERE id=%s""",
                (
                    steps[row['job_type']],
                    worker_context.slot.get(),
                    worker_context.owner.get(),
                    row['job_id'],
                ),
            )
    return Job(
        row['job_id'],
        row['file_id'],
        row['job_type'],
        Path(row['storage_path']),
        Path(row['filename']).suffix.lower()[1:],
        row['duration_ms'],
    )


def fail_dependencies(connection, file_id: int, job_type: str) -> None:
    child = {'pdf_text': 'presentation_analysis', 'video_transcription': 'video_visuals'}.get(job_type)
    if child:
        connection.execute(
            """UPDATE processing_jobs SET status='failed',completed_at=NOW(),
            error_message='A required processing step failed. Retry the file to complete its analysis.'
            WHERE file_id=%s AND job_type=%s AND status='queued'""",
            (file_id, child),
        )


def recover(kind: str, worker_slot: str) -> int:
    # The caller must hold the slot lock. A new slot never fails another live slot.
    with get_connection() as connection:
        rows = connection.execute(
            """UPDATE processing_jobs SET status='failed',completed_at=NOW(),
            error_message='Processing was interrupted. The original is preserved; retry this file.'
            WHERE status='processing' AND job_type=ANY(%s)
            AND (worker_slot=%s OR worker_slot IS NULL OR worker_slot='legacy:0')
            RETURNING file_id,job_type""",
            (TYPES[kind], worker_slot),
        ).fetchall()
        for row in rows:
            fail_dependencies(connection, row['file_id'], row['job_type'])
        return len(rows)


def progress(job_id: int, current: int, total: int, unit: str) -> None:
    if total <= 0 or current < 0:
        return
    # Separate short transactions make progress visible while artifact writes are atomic.
    # The unique process ID prevents an expired owner updating a successor's job.
    with new_connection() as connection:
        connection.execute(
            """UPDATE processing_jobs SET progress_current=%s,progress_total=%s,progress_unit=%s
            WHERE id=%s AND status='processing' AND worker_id IS NOT DISTINCT FROM %s""",
            (min(current, total), total, unit, job_id, worker_context.owner.get()),
        )


def percentage(job: dict) -> int | None:
    if job['status'] == 'completed':
        return 100
    current, total = job.get('progress_current'), job.get('progress_total')
    if current is None or not total or job['status'] == 'queued':
        return None
    return min(100, max(0, current * 100 // total))
