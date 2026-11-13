from datetime import datetime
from typing import Literal

from pydantic import BaseModel, computed_field, field_validator

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
    speaker: str = "Speaker"

    @field_validator("speaker", mode="before")
    @classmethod
    def default_speaker(cls, value: object) -> str:
        """Transcripts saved before speaker identification have NULL speakers."""
        return value.strip() if isinstance(value, str) and value.strip() else "Speaker"


class VideoTranscript(BaseModel):
    file_id: int
    filename: str
    duration_ms: int | None
    language: str | None
    status: Literal["completed"] = "completed"
    segments: list[StoredTranscriptSegment]

    @computed_field
    @property
    def paragraphs(self) -> list[list[int]]:
        """Group segment IDs for reading, keeping one copy of the original text.

        Prefer sentence endings near 600 characters, or pauses of two seconds.
        Segments remain unchanged so search links still identify exact passages.
        """
        paragraphs: list[list[int]] = []
        current: list[int] = []
        length = 0
        previous: StoredTranscriptSegment | None = None
        for segment in self.segments:
            text = " ".join(segment.text.split())
            if not text:
                continue
            if current and previous is not None and (
                segment.speaker != previous.speaker
                or segment.start_ms - previous.end_ms >= 2000
                or (length >= 600 and previous.text.rstrip().endswith((".", "!", "?", "。", "！", "？")))
                or length >= 1000
            ):
                paragraphs.append(current)
                current = []
                length = 0
            current.append(segment.id)
            length += len(text) + 1
            previous = segment
        if current:
            paragraphs.append(current)
        return paragraphs
