from datetime import datetime
from typing import Literal

from pydantic import BaseModel

JobStatus = Literal["queued", "processing", "completed", "failed"]
ProcessingStep = Literal["queued", "validating_video", "extracting_audio", "transcribing_audio", "saving_transcript", "completed"]


class VideoUploadResult(BaseModel):
    file_id: int
    job_id: int
    filename: str
    status: Literal["queued"] = "queued"


class ProcessingJob(BaseModel):
    id: int
    file_id: int
    status: JobStatus
    current_step: ProcessingStep
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class VideoRecord(BaseModel):
    file_id: int
    filename: str
    size_bytes: int
    duration_ms: int | None
    uploaded_at: datetime | None
    job_id: int
    status: JobStatus


class StoredTranscriptSegment(BaseModel):
    id: int
    start_ms: int
    end_ms: int
    text: str


class VideoTranscript(BaseModel):
    file_id: int
    filename: str
    duration_ms: int | None
    language: str | None
    status: Literal["completed"] = "completed"
    segments: list[StoredTranscriptSegment]
