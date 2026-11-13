"""Supported selections describe the current pipelines, including their dependencies."""

from typing import Literal
from pydantic import BaseModel, Field

Operation = Literal['pdf_text', 'slides', 'transcribe', 'visuals', 'storage', 'duplicates']


class ProcessingSelection(BaseModel):
    operations: list[Operation] = Field(min_length=1, max_length=6)
