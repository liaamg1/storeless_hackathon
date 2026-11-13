"""Coordinate validation, local storage, PDF extraction, and persistence."""
import hashlib
import logging
from typing import BinaryIO
from uuid import uuid4

from app.core.config import get_settings
from app.processors.pdf_processor import extract_pdf_pages
from app.repositories.file_repository import create_document
from app.schemas.file import UploadResult

logger = logging.getLogger(__name__)
CHUNK_SIZE = 64 * 1024


class InvalidUploadError(ValueError):
    pass


class UnsupportedFileError(ValueError):
    pass


class UploadTooLargeError(ValueError):
    pass


def save_uploaded_file(source: BinaryIO, target: BinaryIO, limit: int) -> tuple[int, str]:
    """Copy buffered bytes while enforcing the limit and hashing actual content."""
    size_bytes = 0
    digest = hashlib.sha256()
    while chunk := source.read(CHUNK_SIZE):
        size_bytes += len(chunk)
        if size_bytes > limit:
            raise UploadTooLargeError(f"File exceeds the {limit:,}-byte upload limit.")
        digest.update(chunk)
        target.write(chunk)
    if size_bytes == 0:
        raise InvalidUploadError("The uploaded file is empty.")
    return size_bytes, digest.hexdigest()


def upload_pdf(source: BinaryIO, original_filename: str | None) -> UploadResult:
    """Store a PDF and its pages, removing this upload if any step fails."""
    settings = get_settings()
    upload_id = uuid4().hex
    # Client filenames are metadata only; generated names determine storage paths.
    filename = (original_filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    logger.info("upload_received upload_id=%s", upload_id)
    logger.info("validation_started upload_id=%s", upload_id)
    destination = settings.upload_dir / f"{upload_id}.pdf"
    owns_file = False
    try:
        if not filename.lower().endswith(".pdf"):
            raise UnsupportedFileError("Only PDF files are supported.")
        settings.upload_dir.mkdir(parents=True, exist_ok=True)
        # Exclusive creation prevents overwriting an existing path, even on a collision.
        with destination.open("xb") as target:
            owns_file = True
            size_bytes, sha256 = save_uploaded_file(source, target, settings.max_upload_bytes)
        with destination.open("rb") as saved:
            if not saved.read(1024).lstrip().startswith(b"%PDF-"):
                raise UnsupportedFileError("The file contents are not PDF format.")
        logger.info("validation_completed upload_id=%s size_bytes=%s", upload_id, size_bytes)
        logger.info("extraction_started upload_id=%s", upload_id)
        pages = extract_pdf_pages(destination)
        logger.info("extraction_completed upload_id=%s page_count=%s", upload_id, len(pages))
        result = create_document(filename, size_bytes, sha256, destination, pages)
        logger.info("persistence_completed upload_id=%s file_id=%s", upload_id, result.id)
        return result
    except Exception as exc:
        # PostgreSQL rolls back its transaction. Only this upload's file is removed.
        try:
            if owns_file:
                destination.unlink(missing_ok=True)
        except OSError:
            logger.exception("upload_cleanup_failed upload_id=%s", upload_id)
        logger.warning("upload_failed upload_id=%s error_type=%s", upload_id, type(exc).__name__)
        raise
