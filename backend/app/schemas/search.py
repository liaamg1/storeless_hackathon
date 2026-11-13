from pydantic import BaseModel


class SearchResult(BaseModel):
    file_id: int
    filename: str
    page_number: int
    snippet: str
    relevance: float


class SearchResponse(BaseModel):
    query: str
    returned_count: int
    results: list[SearchResult]
