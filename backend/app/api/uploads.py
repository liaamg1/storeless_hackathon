"""Unified orchestration; legacy feature endpoints remain unchanged."""

import json
import logging
from collections.abc import Callable
from typing import TypeVar

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import ValidationError

from app.core.config import get_settings, get_transcription_settings
from app.processors.audio_extractor import MediaProcessingError, MediaToolUnavailableError
from app.processors.pdf_processor import InvalidPdfError
from app.processors.presentation_processor import PresentationProcessingError
from app.schemas.upload import ProcessingSelection
from app.services import upload_service as service
from app.services.file_service import InvalidUploadError, UnsupportedFileError, UploadTooLargeError

router = APIRouter(prefix='/uploads', tags=['unified uploads'])
logger = logging.getLogger(__name__)
T = TypeVar('T')


def response(action: Callable[[], T]) -> T:
    try:
        return action()
    except service.UploadedFileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except UploadTooLargeError as exc:
        raise HTTPException(413, str(exc)) from exc
    except UnsupportedFileError as exc:
        raise HTTPException(415, str(exc)) from exc
    except MediaToolUnavailableError as exc:
        raise HTTPException(503, str(exc)) from exc
    except (InvalidUploadError, InvalidPdfError, PresentationProcessingError, MediaProcessingError) as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.error('unified_upload_failed error_type=%s', type(exc).__name__)
        raise HTTPException(
            500, 'File processing is unavailable. Check Files before retrying; a stored upload can be reused.'
        ) from exc


@router.get('/limits')
def limits() -> dict:
    return response(
        lambda: {
            'pdf': get_settings().max_upload_bytes,
            'pptx': get_settings().max_upload_bytes,
            'video': get_transcription_settings().max_video_bytes,
        }
    )


@router.get('')
def processing_files() -> list[dict]:
    return response(service.history)


@router.post('', status_code=202)
def upload(file: UploadFile = File(...), operations: str = Form(...)) -> dict:
    try:
        try:
            selection = ProcessingSelection(operations=json.loads(operations))
        except (ValueError, TypeError, ValidationError) as exc:
            raise HTTPException(400, 'Choose a valid list of processing operations.') from exc
        return response(lambda: service.upload(file.file, file.filename, selection.operations))
    finally:
        file.file.close()


@router.get('/{file_id}')
def processing_file(file_id: int) -> dict:
    return response(lambda: service.get_processing(file_id))


@router.post('/{file_id}/process', status_code=202)
def process_existing(file_id: int, selection: ProcessingSelection) -> dict:
    def start() -> dict:
        canonical_id = service.coordinate(file_id, selection.operations)
        return service.get_processing(canonical_id)

    return response(start)
