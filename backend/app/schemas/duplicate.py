from datetime import datetime

from pydantic import BaseModel


class DuplicateFile(BaseModel):
    id: int
    filename: str
    size_bytes: int
    uploaded_at: datetime | None


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
