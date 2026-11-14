"""Stream uploads and coordinate the existing background worker and cached artifacts."""

import logging
import os
import shutil
from pathlib import Path
from uuid import uuid4
from typing import BinaryIO

from app.core.config import get_settings
from app.processors.presentation_processor import PresentationProcessingError, extract_slides, validate_pptx
from app.repositories import presentation_repository as repository
from app.repositories.transcription_repository import fail_job, update_job_step
from app.schemas.presentation import PresentationRecord, PresentationComparison
from app.services.file_service import UnsupportedFileError, save_uploaded_file
from app.services.slide_comparison import compare_slides

logger = logging.getLogger(__name__)


class PresentationNotFoundError(ValueError):
    pass


def get_presentation(file_id: int) -> PresentationRecord:
    row = repository.get_source(file_id)
    if row is None:
        raise PresentationNotFoundError('Presentation not found.')
    return PresentationRecord(**row)


def analyze_presentation(file_id: int) -> PresentationRecord:
    row = repository.get_source(file_id)
    if row is None:
        raise PresentationNotFoundError('Presentation not found.')
    if row['status'] in ('completed', 'queued', 'processing'):
        return PresentationRecord(**row)  # Completed images/hashes are reused.
    path = row['storage_path']
    if not path or not Path(path).is_file():
        raise PresentationProcessingError('The original presentation is not available for analysis.')
    return repository.queue_existing(file_id)


def upload_presentation(
    source: BinaryIO, original_filename: str | None, *, processing_options: list[str] | None = None
) -> PresentationRecord:
    settings = get_settings()
    filename = (original_filename or '').replace('\\', '/').rsplit('/', 1)[-1]
    suffix = Path(filename).suffix.lower()
    if suffix not in ('.pdf', '.pptx'):
        raise UnsupportedFileError('Only PDF and PPTX presentations are supported.')
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    target = settings.upload_dir / f'{uuid4().hex}{suffix}'
    owns_file = False
    try:
        with target.open('xb') as destination:
            owns_file = True
            size, digest = save_uploaded_file(source, destination, settings.max_upload_bytes)
        if suffix == '.pptx':
            validate_pptx(target)
        else:
            with target.open('rb') as pdf:
                if not pdf.read(1024).lstrip().startswith(b'%PDF-'):
                    raise UnsupportedFileError('The file contents are not PDF format.')
        return repository.create_presentation(
            filename,
            size,
            digest,
            target,
            processing_options=processing_options,
        )
    except Exception:
        if owns_file:
            target.unlink(missing_ok=True)
        raise


def process_presentation_job(job: repository.PresentationJob) -> None:
    settings = get_settings()
    output = settings.upload_dir / 'slides' / str(job.file_id) / uuid4().hex
    try:
        # A killed process cannot remove its uncommitted render attempt. Clean only
        # UUID directories for this file, preserving every referenced artifact.
        referenced = {Path(path).resolve().parent for path in repository.artifact_paths(job.file_id)}
        if output.parent.is_dir():
            for attempt in output.parent.iterdir():
                if (
                    len(attempt.name) == 32
                    and all(c in '0123456789abcdef' for c in attempt.name)
                    and attempt.is_dir()
                    and not attempt.is_symlink()
                    and attempt.resolve() not in referenced
                ):
                    shutil.rmtree(attempt)
        timeout = int(os.getenv('PRESENTATION_RENDER_TIMEOUT_SECONDS', '120'))
        maximum = int(os.getenv('PRESENTATION_MAX_SLIDES', '500'))
        if timeout <= 0 or maximum <= 0:
            raise PresentationProcessingError('Presentation timeout and slide limit must be positive.')
        logger.info('presentation_rendering_started job_id=%s file_id=%s', job.job_id, job.file_id)
        from app.repositories.job_repository import progress

        slides = list(
            extract_slides(
                job.storage_path,
                job.kind,
                output,
                office_binary=os.getenv('LIBREOFFICE_BINARY', 'libreoffice'),
                timeout=timeout,
                max_slides=maximum,
                on_progress=lambda done, total: progress(job.job_id, done, total, 'slides'),
            )
        )
        update_job_step(job.job_id, 'saving_slides')
        repository.complete_presentation(job, slides)
        logger.info('presentation_completed job_id=%s slide_count=%s', job.job_id, len(slides))
    except Exception as exc:
        # Only this attempt's generated directory is removed. Originals and any
        # previously committed artifacts are never deleted by analysis failure.
        if output.is_dir():
            shutil.rmtree(output)
        logger.error('presentation_processing_failed job_id=%s error_type=%s', job.job_id, type(exc).__name__)
        message = (
            str(exc)
            if isinstance(exc, PresentationProcessingError)
            else 'Presentation analysis failed. The original file is preserved.'
        )
        fail_job(job.job_id, message)


def get_comparison(file_id: int) -> PresentationComparison:
    presentation = get_presentation(file_id)
    threshold = float(os.getenv('SLIDE_SIMILARITY_THRESHOLD', '90'))
    if not 0 <= threshold <= 100:
        raise ValueError('SLIDE_SIMILARITY_THRESHOLD must be between 0 and 100.')
    return compare_slides(presentation, repository.get_analyzed_slides(), threshold)


def resolve_image(slide_id: int, thumbnail: bool) -> Path:
    stored = repository.get_slide_path(slide_id, thumbnail)
    root = (get_settings().upload_dir / 'slides').resolve()
    path = Path(stored).resolve() if stored else None
    if path is None or not path.is_relative_to(root) or not path.is_file():
        raise PresentationNotFoundError('Slide image not found.')
    return path
