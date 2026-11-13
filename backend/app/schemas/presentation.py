from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class PresentationRecord(BaseModel):
    file_id: int
    filename: str
    size_bytes: int
    uploaded_at: datetime | None
    job_id: int | None
    status: Literal['not_processed', 'queued', 'processing', 'completed', 'failed']
    current_step: str | None
    error_message: str | None
    slide_count: int


class SlidePreview(BaseModel):
    id: int
    file_id: int
    filename: str
    slide_number: int
    text: str
    processed_at: datetime


class SlideMatch(BaseModel):
    slide: SlidePreview
    classification: Literal['exact', 'similar']
    similarity_percent: float
    hash_distance: int


class SlideComparison(BaseModel):
    slide: SlidePreview
    classification: Literal['exact', 'similar', 'unique']
    matches: list[SlideMatch]


class SlideSummary(BaseModel):
    presentations_analyzed: int
    total_slides_analyzed: int
    selected_slide_count: int
    exact_slides: int
    similar_slides: int
    unique_slides: int
    matching_presentations: int


class PresentationComparison(BaseModel):
    presentation: PresentationRecord
    similarity_threshold: float
    summary: SlideSummary
    slides: list[SlideComparison]
