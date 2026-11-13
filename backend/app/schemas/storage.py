"""Byte measurements for generated output files, independent of display rounding."""
from typing import Literal

from pydantic import BaseModel, computed_field


class StorageComponent(BaseModel):
    kind: Literal['transcript', 'images', 'other']
    label: str
    status: Literal['measured', 'not_generated', 'unavailable']
    size_bytes: int | None = None
    file_count: int | None = None


class StorageSavings(BaseModel):
    file_id: int
    filename: str
    status: Literal['completed', 'processing', 'failed', 'unavailable']
    message: str
    original_size_bytes: int
    optimized_size_bytes: int | None = None
    artifact_format: Literal['txt', 'html'] | None = None
    download_url: str | None = None
    payload_size_bytes: int | None = None
    components: list[StorageComponent]

    @computed_field
    @property
    def original_size_mb(self) -> float:
        return self.original_size_bytes / 1_000_000

    @computed_field
    @property
    def optimized_size_mb(self) -> float | None:
        return None if self.optimized_size_bytes is None else self.optimized_size_bytes / 1_000_000

    @computed_field
    @property
    def storage_saved_bytes(self) -> int | None:
        if self.optimized_size_bytes is None:
            return None
        # A larger output is a negative saving, never silently clamped to zero.
        return self.original_size_bytes - self.optimized_size_bytes

    @computed_field
    @property
    def storage_saved_mb(self) -> float | None:
        return None if self.storage_saved_bytes is None else self.storage_saved_bytes / 1_000_000

    @computed_field
    @property
    def reduction_percent(self) -> float | None:
        if self.storage_saved_bytes is None or self.original_size_bytes <= 0:
            return None
        return self.storage_saved_bytes / self.original_size_bytes * 100
