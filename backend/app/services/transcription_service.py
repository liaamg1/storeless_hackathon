"""Video upload coordination and one-job processing pipeline."""
import logging
from tempfile import TemporaryDirectory
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from app.core.config import get_settings, get_transcription_settings
from app.processors.audio_extractor import MediaProcessingError, MediaToolUnavailableError, extract_audio, validate_video
from app.processors.speech_recognizer import SpeechRecognitionError, transcribe_audio
from app.repositories import transcription_repository as repository
from app.schemas.transcription import VideoUploadResult
from app.services.file_service import UnsupportedFileError, save_uploaded_file

logger = logging.getLogger(__name__)


def upload_video(source: BinaryIO, original_filename: str | None) -> VideoUploadResult:
    """Stream/hash an MP4, validate real media, then commit metadata and a queued job."""
    settings = get_settings()
    video_settings = get_transcription_settings()
    filename = (original_filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    upload_id = uuid4().hex
    logger.info("video_upload_received upload_id=%s", upload_id)
    if not filename.lower().endswith('.mp4'):
        raise UnsupportedFileError("Only MP4 recordings are supported.")
    destination = settings.upload_dir / f"{upload_id}.mp4"
    owns_file = False
    try:
        settings.upload_dir.mkdir(parents=True, exist_ok=True)
        with destination.open('xb') as target:
            owns_file = True
            size_bytes, sha256 = save_uploaded_file(source, target, video_settings.max_video_bytes)
        metadata = validate_video(destination, video_settings.ffprobe)
        logger.info("video_validated upload_id=%s size_bytes=%s duration_ms=%s", upload_id, size_bytes, metadata.duration_ms)
        result = repository.create_video_job(filename, size_bytes, sha256, destination, metadata.duration_ms)
        logger.info("video_queued file_id=%s job_id=%s", result.file_id, result.job_id)
        return result
    except Exception as exc:
        # Cleanup applies only before a job is committed. Worker failures preserve MP4s.
        if owns_file:
            try:
                destination.unlink(missing_ok=True)
            except OSError:
                logger.error("video_upload_cleanup_failed upload_id=%s", upload_id)
        logger.warning("video_upload_failed upload_id=%s error_type=%s", upload_id, type(exc).__name__)
        raise


def process_video_job(job: repository.ClaimedVideoJob) -> None:
    """Advance real processing stages and preserve the original recording on failure."""
    settings = get_transcription_settings()
    try:
        logger.info("video_validation_started job_id=%s file_id=%s", job.job_id, job.file_id)
        validate_video(job.storage_path, settings.ffprobe)
        logger.info("video_validated job_id=%s", job.job_id)
        # WAV data is temporary: no database storage and cleanup on normal failure/success.
        with TemporaryDirectory(prefix=f"restore-audio-{job.job_id}-") as temporary_dir:
            repository.update_job_step(job.job_id, 'extracting_audio')
            logger.info("audio_extraction_started job_id=%s", job.job_id)
            audio_path = extract_audio(job.storage_path, Path(temporary_dir) / 'audio.wav',
                                       settings.ffmpeg, settings.media_timeout)
            logger.info("audio_extraction_completed job_id=%s", job.job_id)
            repository.update_job_step(job.job_id, 'transcribing_audio')
            logger.info("transcription_started job_id=%s", job.job_id)
            def report_progress(processed_ms: int, total_ms: int) -> None:
                logger.info("transcription_progress job_id=%s processed_ms=%s total_ms=%s",
                            job.job_id, processed_ms, total_ms)

            result = transcribe_audio(
                audio_path, model_name=settings.model_name, device=settings.device,
                compute_type=settings.compute_type, language=settings.language,
                download_root=settings.download_root,
                chunk_seconds=settings.chunk_seconds, cpu_threads=settings.cpu_threads,
                on_progress=report_progress,
            )
            logger.info("transcription_completed job_id=%s segment_count=%s", job.job_id, len(result.segments))
            repository.update_job_step(job.job_id, 'saving_transcript')
            repository.complete_transcription(job, result)
            logger.info("transcript_saved job_id=%s file_id=%s", job.job_id, job.file_id)
            logger.info("processing_job_completed job_id=%s", job.job_id)
    except Exception as exc:
        logger.error("video_processing_failed job_id=%s error_type=%s", job.job_id, type(exc).__name__)
        message = str(exc) if isinstance(exc, (MediaProcessingError, MediaToolUnavailableError, SpeechRecognitionError)) else (
            "Processing failed while reading the recording or saving its transcript. The original recording is preserved."
        )
        try:
            repository.fail_job(job.job_id, message)
        except Exception as status_error:
            # Recovery on worker restart marks jobs that could not be updated during a DB outage.
            logger.error("job_failure_update_failed job_id=%s error_type=%s", job.job_id, type(status_error).__name__)
            raise RuntimeError("Could not persist job failure; restart the worker to recover it.") from None
