from typing import Literal

from pydantic import BaseModel


class SearchResult(BaseModel):
    file_id: int
    filename: str
    file_type: Literal["pdf", "pptx"] = "pdf"
    page_number: int
    snippet: str
    relevance: float


class SearchVisual(BaseModel):
    id: int
    start_ms: int
    end_ms: int


class VideoSearchResult(BaseModel):
    file_id: int
    filename: str
    file_type: Literal["video"] = "video"
    segment_id: int
    start_ms: int
    end_ms: int
    snippet: str
    relevance: float
    visual: SearchVisual | None = None


class SearchResponse(BaseModel):
    query: str
    returned_count: int
    results: list[SearchResult | VideoSearchResult]
