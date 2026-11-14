from datetime import datetime

from pydantic import BaseModel, Field


class DuplicateFile(BaseModel):
    id: int
    filename: str
    size_bytes: int
    uploaded_at: datetime | None
    completed_operations: list[str] = Field(default_factory=list)


class DuplicateGroup(BaseModel):
    sha256: str
    file_size_bytes: int
    file_count: int
    potential_savings_bytes: int
    files: list[DuplicateFile]


class DuplicateSummary(BaseModel):
    duplicate_groups: int
    redundant_copies: int
    potential_savings_bytes: int


class DuplicateResponse(BaseModel):
    summary: DuplicateSummary
    groups: list[DuplicateGroup]
