import logging

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.processors.pdf_processor import InvalidPdfError
from app.repositories import file_repository
from app.schemas.file import DocumentDetails, FileRecord, UploadResult
from app.services.file_service import (
    InvalidUploadError, UnsupportedFileError, UploadTooLargeError, upload_pdf,
)

router = APIRouter(prefix="/files", tags=["files"])
logger = logging.getLogger(__name__)


@router.get("", response_model=list[FileRecord])
def get_files() -> list[FileRecord]:
    return file_repository.list_files()


@router.post("/upload", response_model=UploadResult, status_code=201)
def upload_file(file: UploadFile = File(...)) -> UploadResult:
    # A sync handler keeps filesystem, parsing, and psycopg work off the event loop.
    try:
        return upload_pdf(file.file, file.filename)
    except (InvalidUploadError, InvalidPdfError) as exc:
        raise HTTPException(400, str(exc)) from exc
    except UploadTooLargeError as exc:
        raise HTTPException(413, str(exc)) from exc
    except UnsupportedFileError as exc:
        raise HTTPException(415, str(exc)) from exc
    except Exception as exc:
        # Database exception messages can contain row contents; log only the type.
        logger.error("upload_internal_failure error_type=%s", type(exc).__name__)
        raise HTTPException(500, "Could not store or process the PDF. Please try again.") from exc
    finally:
        file.file.close()


@router.get("/{file_id}/pages", response_model=DocumentDetails)
def get_pages(file_id: int) -> DocumentDetails:
    document = file_repository.get_document_pages(file_id)
    if document is None:
        raise HTTPException(404, "File not found.")
    return document
