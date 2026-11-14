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
                WHERE files.original_removed_at IS NULL
                UNION ALL
                SELECT files.id, files.filename, 'video', NULL::integer,
                       segments.id, segments.start_ms, segments.end_ms, segments.text
                FROM transcript_segments AS segments
                JOIN files ON files.id = segments.file_id
                JOIN processing_jobs AS jobs ON jobs.file_id = files.id
                WHERE files.original_removed_at IS NULL AND files.file_type = 'video'
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
            SELECT matches.file_id, filename, file_type, page_number, segment_id,
                   matches.start_ms, matches.end_ms, relevance,
                   visual.id AS visual_id, visual.start_ms AS visual_start_ms, visual.end_ms AS visual_end_ms,
                   ts_headline('simple', text, terms,
                       'StartSel="", StopSel="", MaxWords=35, MinWords=15, MaxFragments=1'
                   ) AS snippet
            FROM matches
            LEFT JOIN LATERAL (
                SELECT frame.id, frame.start_ms, frame.end_ms FROM video_frames frame
                JOIN processing_jobs job ON job.file_id=frame.file_id
                  AND job.job_type='video_visuals' AND job.status='completed'
                WHERE matches.file_type='video' AND frame.file_id=matches.file_id
                  AND matches.end_ms > matches.start_ms
                  AND frame.start_ms < matches.end_ms AND frame.end_ms > matches.start_ms
                ORDER BY LEAST(frame.end_ms,matches.end_ms)-GREATEST(frame.start_ms,matches.start_ms) DESC,
                         frame.start_ms,frame.id LIMIT 1
            ) visual ON TRUE
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
        visual = ({'id': row['visual_id'], 'start_ms': row['visual_start_ms'], 'end_ms': row['visual_end_ms']}
                  if row['visual_id'] is not None else None)
        results.append(result_type(**{**row, "snippet": snippet, 'visual': visual}))
    return results
