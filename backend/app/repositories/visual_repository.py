"""Independent visual jobs preserve completed speech transcripts on failure."""
from app.core.database import get_connection
from app.processors.video_visuals import ExtractedFrame


def queue(file_id: int) -> None:
    with get_connection() as connection:
        connection.execute(
            """INSERT INTO processing_jobs (file_id, job_type) VALUES (%s, 'video_visuals')
               ON CONFLICT (file_id, job_type) DO UPDATE SET status='queued', current_step='queued',
               error_message=NULL, started_at=NULL, completed_at=NULL
               WHERE processing_jobs.status='failed'""", (file_id,),
        )


def state(file_id: int) -> dict | None:
    with get_connection() as connection:
        return connection.execute(
            """SELECT status, current_step, error_message FROM processing_jobs
               WHERE file_id=%s AND job_type='video_visuals'""", (file_id,),
        ).fetchone()


def claim() -> dict | None:
    with get_connection() as connection:
        with connection.transaction():
            row = connection.execute(
                """SELECT j.id AS job_id, j.file_id, f.storage_path, f.duration_ms
                   FROM processing_jobs j JOIN files f ON f.id=j.file_id
                   JOIN processing_jobs speech ON speech.file_id=f.id
                     AND speech.job_type='video_transcription' AND speech.status='completed'
                   WHERE j.job_type='video_visuals' AND j.status='queued' ORDER BY j.id
                   FOR UPDATE OF j SKIP LOCKED LIMIT 1""",
            ).fetchone()
            if row:
                connection.execute(
                    """UPDATE processing_jobs SET status='processing', current_step='extracting_visuals',
                       started_at=NOW() WHERE id=%s""", (row['job_id'],),
                )
    return row


def complete(job: dict, frames: list[ExtractedFrame]) -> None:
    with get_connection() as connection:
        with connection.transaction():
            row = connection.execute(
                'SELECT status FROM processing_jobs WHERE id=%s FOR UPDATE', (job['job_id'],),
            ).fetchone()
            if not row or row['status'] != 'processing':
                raise ValueError('Visual job is no longer processing.')
            with connection.cursor() as cursor:
                cursor.executemany(
                    """INSERT INTO video_frames (file_id, start_ms, end_ms, image_path, image_hash, size_bytes)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    [(job['file_id'], f.start_ms, f.end_ms, str(f.image_path), f.image_hash, f.size_bytes) for f in frames],
                )
            connection.execute(
                """UPDATE processing_jobs SET status='completed', current_step='completed',
                   error_message=NULL, completed_at=NOW() WHERE id=%s""", (job['job_id'],),
            )


def frames(file_id: int) -> list[dict]:
    with get_connection() as connection:
        return connection.execute(
            """SELECT id, file_id, start_ms, end_ms, image_path, image_hash, size_bytes
               FROM video_frames WHERE file_id=%s ORDER BY start_ms, id""", (file_id,),
        ).fetchall()
