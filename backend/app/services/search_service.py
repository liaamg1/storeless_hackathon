from app.repositories.search_repository import get_matching_pages
from app.schemas.search import SearchResponse


class InvalidSearchQuery(ValueError):
    """Search input does not satisfy the public query constraints."""


def search_document_pages(query: str, limit: int = 20) -> SearchResponse:
    """Search stored PDF pages with PostgreSQL web-search semantics.

    The 'simple' configuration preserves technical terms without language-specific
    stemming. Whitespace is normalized without removing quotes or exclusion syntax.
    returned_count describes this limited result set, not the number of all matches.
    """
    normalized_query = " ".join(query.split())
    if not normalized_query or len(query) > 200 or "\x00" in query:
        raise InvalidSearchQuery("Search must contain 1–200 characters and no null characters.")
    if not 1 <= limit <= 100:
        raise InvalidSearchQuery("Result limit must be between 1 and 100.")
    results = get_matching_pages(normalized_query, limit)
    return SearchResponse(
        query=normalized_query, returned_count=len(results), results=results,
    )
