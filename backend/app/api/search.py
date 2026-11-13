import logging

from fastapi import APIRouter, HTTPException, Query

from app.schemas.search import SearchResponse
from app.services.search_service import InvalidSearchQuery, search_document_pages

router = APIRouter(tags=["search"])
logger = logging.getLogger(__name__)


@router.get("/search", response_model=SearchResponse)
def search_documents(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(20, ge=1, le=100),
) -> SearchResponse:
    try:
        return search_document_pages(q, limit)
    except InvalidSearchQuery as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        # Exception messages can contain SQL or document text; log only the type.
        logger.error("document_search_failed error_type=%s", type(exc).__name__)
        raise HTTPException(500, "Document search is unavailable. Please try again.") from exc
