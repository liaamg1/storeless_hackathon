from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class FileRecord(BaseModel):
    id: int
    filename: str
    size_bytes: int
    sha256: str
    uploaded_at: datetime | None


class UploadResult(BaseModel):
    id: int
    filename: str
    size_bytes: int
    page_count: int
    status: Literal["completed"] = "completed"


class DocumentPage(BaseModel):
    page_number: int
    text: str


class DocumentDetails(BaseModel):
    file_id: int
    filename: str
    size_bytes: int
    page_count: int
    status: Literal["completed", "not_processed"]
    pages: list[DocumentPage]
