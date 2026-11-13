"""PostgreSQL full-text matching, ranking, and plain-text excerpts."""
from app.core.database import get_connection
from app.schemas.search import SearchResult

MAX_SNIPPET_LENGTH = 500


def get_matching_pages(query: str, limit: int) -> list[SearchResult]:
    """Read stored text using the same 'simple' configuration as the GIN index.

    Cover-density ranking rewards nearby terms and repeated matches. Equal ranks
    are ordered by file ID and page number so repeated requests stay predictable.
    Only the limited result set is passed to ts_headline, which is relatively costly.
    """
    with get_connection() as connection:
        rows = connection.execute(
            """
            WITH search_query AS (
                SELECT websearch_to_tsquery('simple', %s) AS terms
            ), matches AS MATERIALIZED (
                SELECT files.id AS file_id, files.filename, pages.page_number,
                       pages.extracted_text, search_query.terms,
                       ts_rank_cd(to_tsvector('simple', pages.extracted_text),
                                  search_query.terms) AS relevance
                FROM document_pages AS pages
                JOIN files ON files.id = pages.file_id
                CROSS JOIN search_query
                WHERE to_tsvector('simple', pages.extracted_text) @@ search_query.terms
                ORDER BY relevance DESC, files.id, pages.page_number
                LIMIT %s
            )
            SELECT file_id, filename, page_number, relevance,
                   ts_headline('simple', extracted_text, terms,
                       'StartSel="", StopSel="", MaxWords=35, MinWords=15, MaxFragments=1'
                   ) AS snippet
            FROM matches
            ORDER BY relevance DESC, file_id, page_number
            """,
            (query, limit),
        ).fetchall()
    results = []
    for row in rows:
        # Word limits alone cannot bound very long technical tokens.
        snippet = " ".join(row["snippet"].split())
        if len(snippet) > MAX_SNIPPET_LENGTH:
            snippet = snippet[:MAX_SNIPPET_LENGTH - 3] + "..."
        results.append(SearchResult(**{**row, "snippet": snippet}))
    return results
