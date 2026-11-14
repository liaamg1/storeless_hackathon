import logging
from collections.abc import Callable
from typing import TypeVar

from fastapi import APIRouter, File, HTTPException, UploadFile, Query
from fastapi.responses import FileResponse

from app.processors.presentation_processor import PresentationProcessingError
from app.repositories.presentation_repository import list_presentations
from app.schemas.presentation import PresentationRecord, PresentationComparison
from app.services import presentation_service as service
from app.services.file_service import InvalidUploadError, UnsupportedFileError, UploadTooLargeError

router = APIRouter(prefix='/presentations', tags=['presentations'])
logger = logging.getLogger(__name__)
T = TypeVar('T')


def presentation_response(action: Callable[[], T]) -> T:
    try:
        return action()
    except service.PresentationNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except UploadTooLargeError as exc:
        raise HTTPException(413, str(exc)) from exc
    except UnsupportedFileError as exc:
        raise HTTPException(415, str(exc)) from exc
    except (PresentationProcessingError, InvalidUploadError) as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.error('presentation_request_failed error_type=%s', type(exc).__name__)
        raise HTTPException(500, 'Presentation analysis is unavailable. Please try again.') from exc


@router.get('', response_model=list[PresentationRecord])
def presentations() -> list[PresentationRecord]:
    return presentation_response(list_presentations)


@router.post('/upload', response_model=PresentationRecord, status_code=202)
def upload(file: UploadFile = File(...)) -> PresentationRecord:
    try:
        return presentation_response(lambda: service.upload_presentation(file.file, file.filename))
    finally:
        file.file.close()


@router.get('/slides/{slide_id}/image')
def slide_image(slide_id: int, thumbnail: bool = Query(True)) -> FileResponse:
    path = presentation_response(lambda: service.resolve_image(slide_id, thumbnail))
    return FileResponse(path, media_type='image/png', headers={'Cache-Control': 'private, max-age=3600'})


@router.get('/{file_id}', response_model=PresentationRecord)
def presentation(file_id: int) -> PresentationRecord:
    return presentation_response(lambda: service.get_presentation(file_id))


@router.post('/{file_id}/analyze', response_model=PresentationRecord, status_code=202)
def analyze(file_id: int) -> PresentationRecord:
    return presentation_response(lambda: service.analyze_presentation(file_id))


@router.get('/{file_id}/comparison', response_model=PresentationComparison)
def comparison(file_id: int) -> PresentationComparison:
    return presentation_response(lambda: service.get_comparison(file_id))


@router.get('/slides/{slide_id}/revisions/{other_id}')
def slide_revision(slide_id: int, other_id: int) -> dict:
    from app.services.slide_revision import revision
    return presentation_response(lambda: revision(slide_id,other_id))
