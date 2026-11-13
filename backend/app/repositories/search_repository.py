"""PostgreSQL full-text matching, ranking, and plain-text excerpts."""
from app.core.database import get_connection
from app.schemas.search import SearchResult, VideoSearchResult

MAX_SNIPPET_LENGTH = 500


def get_matching_content(query: str, limit: int) -> list[SearchResult | VideoSearchResult]:
    """Read stored text using the same 'simple' configuration as the GIN index.

    Cover-density ranking rewards nearby terms and repeated matches. Equal ranks
    are ordered by file ID and location so repeated requests stay predictable.
    Only the limited result set is passed to ts_headline, which is relatively costly.
    """
    with get_connection() as connection:
        rows = connection.execute(
            """
            WITH search_query AS (
                SELECT websearch_to_tsquery('simple', %s) AS terms
            ), content AS (
                SELECT files.id AS file_id, files.filename,
                       CASE WHEN lower(files.filename) LIKE '%%.pptx' THEN 'pptx' ELSE 'pdf' END AS file_type,
                       pages.page_number, NULL::integer AS segment_id,
                       NULL::bigint AS start_ms, NULL::bigint AS end_ms,
                       pages.extracted_text AS text
                FROM document_pages AS pages
                JOIN files ON files.id = pages.file_id
                UNION ALL
                SELECT files.id, files.filename, 'video', NULL::integer,
                       segments.id, segments.start_ms, segments.end_ms, segments.text
                FROM transcript_segments AS segments
                JOIN files ON files.id = segments.file_id
                JOIN processing_jobs AS jobs ON jobs.file_id = files.id
                WHERE files.file_type = 'video'
                  AND jobs.job_type = 'video_transcription' AND jobs.status = 'completed'
            ), matches AS MATERIALIZED (
                SELECT content.*, search_query.terms,
                       ts_rank_cd(to_tsvector('simple', content.text),
                                  search_query.terms) AS relevance
                FROM content
                CROSS JOIN search_query
                WHERE to_tsvector('simple', content.text) @@ search_query.terms
                ORDER BY relevance DESC, file_id, page_number, start_ms, segment_id
                LIMIT %s
            )
            SELECT file_id, filename, file_type, page_number, segment_id,
                   start_ms, end_ms, relevance,
                   ts_headline('simple', text, terms,
                       'StartSel="", StopSel="", MaxWords=35, MinWords=15, MaxFragments=1'
                   ) AS snippet
            FROM matches
            ORDER BY relevance DESC, file_id, page_number, start_ms, segment_id
            """,
            (query, limit),
        ).fetchall()
    results = []
    for row in rows:
        # Word limits alone cannot bound very long technical tokens.
        snippet = " ".join(row["snippet"].split())
        if len(snippet) > MAX_SNIPPET_LENGTH:
            snippet = snippet[:MAX_SNIPPET_LENGTH - 3] + "..."
        result_type = VideoSearchResult if row["file_type"] == "video" else SearchResult
        results.append(result_type(**{**row, "snippet": snippet}))
    return results
