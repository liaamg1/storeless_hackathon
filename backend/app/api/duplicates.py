import logging
from uuid import UUID

from pydantic import BaseModel, Field
from app.services import duplicate_cleanup

from fastapi import APIRouter, HTTPException

from app.schemas.duplicate import DuplicateResponse
from app.services.duplicate_service import get_duplicate_summary

router = APIRouter(tags=["duplicates"])
logger = logging.getLogger(__name__)


@router.get("/duplicates", response_model=DuplicateResponse)
def get_duplicates() -> DuplicateResponse:
    try:
        return get_duplicate_summary()
    except Exception as exc:
        # Database exception messages may include credentials or row contents.
        logger.error("duplicate_scan_failed error_type=%s", type(exc).__name__)
        raise HTTPException(500, "Duplicate scan is unavailable. Please try again.") from exc


class CleanupSelection(BaseModel):
    keeper_id: int = Field(gt=0)
    member_ids: list[int] = Field(min_length=2, max_length=1000)
    confirmed: bool = False


def cleanup_response(action):
    try:
        return action()
    except duplicate_cleanup.CleanupConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        logger.error('duplicate_cleanup_failed error_type=%s', type(exc).__name__)
        raise HTTPException(
            500,
            'Cleanup could not finish. Check its history before retrying; the retained copy is protected.',
        ) from exc


@router.get('/duplicates/resolutions')
def resolutions() -> list[dict]:
    return cleanup_response(duplicate_cleanup.history)


@router.post('/duplicates/cleanup')
def cleanup(selection: CleanupSelection) -> dict:
    return cleanup_response(
        lambda: duplicate_cleanup.cleanup(selection.keeper_id, selection.member_ids, selection.confirmed)
    )


@router.post('/duplicates/resolutions/{resolution_id}/finish')
def finish_cleanup(resolution_id: UUID) -> dict:
    return cleanup_response(lambda: duplicate_cleanup.finish(resolution_id))
