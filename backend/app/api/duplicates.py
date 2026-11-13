import logging

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
