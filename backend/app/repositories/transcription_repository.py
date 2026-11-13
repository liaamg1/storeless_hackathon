"""PostgreSQL job queue, video metadata, and atomic transcript persistence."""
from dataclasses import dataclass
from pathlib import Path

from app.core.database import get_connection
from app.processors.speech_recognizer import TranscriptionResult
from app.schemas.transcription import ProcessingJob, VideoRecord, VideoTranscript, VideoUploadResult


@dataclass(frozen=True)
class ClaimedVideoJob:
    job_id: int
    file_id: int
    storage_path: Path


def create_video_job(filename: str, size_bytes: int, sha256: str,
                     storage_path: Path, duration_ms: int) -> VideoUploadResult:
    """Commit the original's metadata and queued job together, or neither."""
    with get_connection() as connection:
        with connection.transaction():
            file_id = connection.execute(
                """INSERT INTO files (filename, size_bytes, sha256, storage_path, file_type, duration_ms)
                   VALUES (%s, %s, %s, %s, 'video', %s) RETURNING id""",
                (filename, size_bytes, sha256, str(storage_path), duration_ms),
            ).fetchone()["id"]
            job_id = connection.execute(
                """INSERT INTO processing_jobs (file_id, job_type)
                   VALUES (%s, 'video_transcription') RETURNING id""", (file_id,),
            ).fetchone()["id"]
    return VideoUploadResult(file_id=file_id, job_id=job_id, filename=filename)


def list_videos() -> list[VideoRecord]:
    with get_connection() as connection:
        rows = connection.execute(
            """SELECT f.id AS file_id, f.filename, f.size_bytes, f.duration_ms, f.uploaded_at,
                      j.id AS job_id, j.status
               FROM files f JOIN processing_jobs j ON j.file_id = f.id
               WHERE j.job_type = 'video_transcription'
               ORDER BY f.uploaded_at DESC NULLS LAST, f.id DESC"""
        ).fetchall()
    return [VideoRecord(**row) for row in rows]


def get_video(file_id: int) -> VideoRecord | None:
    with get_connection() as connection:
        row = connection.execute(
            """SELECT f.id AS file_id, f.filename, f.size_bytes, f.duration_ms, f.uploaded_at,
                      j.id AS job_id, j.status
               FROM files f JOIN processing_jobs j ON j.file_id = f.id
               WHERE f.id = %s AND j.job_type = 'video_transcription'""", (file_id,),
        ).fetchone()
    return VideoRecord(**row) if row else None


def get_job(job_id: int) -> ProcessingJob | None:
    with get_connection() as connection:
        row = connection.execute(
            """SELECT id, file_id, status, current_step, error_message,
                      created_at, started_at, completed_at FROM processing_jobs
               WHERE id = %s AND job_type = 'video_transcription'""", (job_id,),
        ).fetchone()
    return ProcessingJob(**row) if row else None


def claim_next_job() -> ClaimedVideoJob | None:
    """Claim and commit a queued job before doing slow filesystem/model work."""
    with get_connection() as connection:
        with connection.transaction():
            job = connection.execute(
                """SELECT j.id AS job_id, j.file_id, f.storage_path
                   FROM processing_jobs j JOIN files f ON f.id = j.file_id
                   WHERE j.job_type = 'video_transcription' AND j.status = 'queued'
                   ORDER BY j.id FOR UPDATE OF j SKIP LOCKED LIMIT 1"""
            ).fetchone()
            if job is None:
                return None
            connection.execute(
                """UPDATE processing_jobs SET status = 'processing', current_step = 'validating_video',
                   started_at = NOW(), error_message = NULL WHERE id = %s""", (job["job_id"],),
            )
    return ClaimedVideoJob(job["job_id"], job["file_id"], Path(job["storage_path"]))


def update_job_step(job_id: int, step: str) -> None:
    with get_connection() as connection:
        connection.execute(
            "UPDATE processing_jobs SET current_step = %s WHERE id = %s AND status = 'processing'",
            (step, job_id),
        )


def fail_job(job_id: int, message: str) -> None:
    with get_connection() as connection:
        connection.execute(
            """UPDATE processing_jobs SET status = 'failed', error_message = %s, completed_at = NOW()
               WHERE id = %s AND status = 'processing'""", (message, job_id),
        )


def fail_interrupted_jobs() -> int:
    """Called only after the worker holds the exclusive session advisory lock."""
    with get_connection() as connection:
        return connection.execute(
            """UPDATE processing_jobs SET status = 'failed', completed_at = NOW(),
               error_message = CASE WHEN job_type='presentation_analysis' THEN
                   'Presentation analysis was interrupted. The original file is preserved.'
                   WHEN job_type='video_visuals' THEN
                   'Visual analysis was interrupted. The speech transcript is preserved; retry visual analysis.' ELSE
                   'Processing was interrupted by a worker restart. The original recording is preserved.' END
               WHERE job_type IN ('video_transcription', 'presentation_analysis', 'video_visuals') AND status = 'processing'"""
        ).rowcount


def complete_transcription(job: ClaimedVideoJob, result: TranscriptionResult) -> None:
    """Commit every segment and completion status atomically, including empty speech."""
    with get_connection() as connection:
        with connection.transaction():
            current = connection.execute(
                "SELECT status FROM processing_jobs WHERE id = %s FOR UPDATE", (job.job_id,),
            ).fetchone()
            if current is None or current["status"] != 'processing':
                raise ValueError("The transcription job is no longer processing.")
            with connection.cursor() as cursor:
                cursor.executemany(
                    """INSERT INTO transcript_segments (file_id, start_ms, end_ms, text)
                       VALUES (%s, %s, %s, %s)""",
                    [(job.file_id, segment.start_ms, segment.end_ms, segment.text) for segment in result.segments],
                )
            connection.execute(
                "UPDATE files SET transcript_language = %s WHERE id = %s", (result.language, job.file_id),
            )
            connection.execute(
                """UPDATE processing_jobs SET status = 'completed', current_step = 'completed',
                   error_message = NULL, completed_at = NOW() WHERE id = %s""", (job.job_id,),
            )
            connection.execute(
                """INSERT INTO processing_jobs (file_id, job_type) VALUES (%s, 'video_visuals')
                   ON CONFLICT (file_id, job_type) DO NOTHING""", (job.file_id,),
            )


def get_transcript(file_id: int) -> VideoTranscript:
    """Read only completed transcripts; pending/failed jobs are not empty success."""
    with get_connection() as connection:
        file = connection.execute(
            """SELECT f.filename, f.duration_ms, f.transcript_language AS language,
                      j.status, j.current_step, j.error_message
               FROM files f JOIN processing_jobs j ON j.file_id = f.id
               WHERE f.id = %s AND j.job_type = 'video_transcription'""", (file_id,),
        ).fetchone()
        if file is None:
            raise VideoNotFoundError("Recording not found.")
        if file["status"] != 'completed':
            raise TranscriptNotReadyError(file["status"], file["current_step"], file["error_message"])
        rows = connection.execute(
            """SELECT id, start_ms, end_ms, text FROM transcript_segments
               WHERE file_id = %s ORDER BY start_ms, end_ms, id""", (file_id,),
        ).fetchall()
    return VideoTranscript(file_id=file_id, filename=file["filename"], duration_ms=file["duration_ms"],
                           language=file["language"], segments=rows)


class VideoNotFoundError(ValueError):
    pass


class TranscriptNotReadyError(ValueError):
    def __init__(self, status: str, current_step: str, error_message: str | None):
        self.status = status
        self.current_step = current_step
        self.error_message = error_message
        super().__init__(f"Transcript is not available: job is {status}.")
