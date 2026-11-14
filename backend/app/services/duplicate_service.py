"""Derive duplicate summaries without changing metadata or physical storage."""
from app.repositories.duplicate_repository import find_duplicate_file_groups
from app.schemas.duplicate import DuplicateGroup, DuplicateResponse, DuplicateSummary


def calculate_potential_savings(file_count: int, file_size_bytes: int) -> int:
    """Estimate savings if one copy is kept and all others occupy separate storage.

    Integer arithmetic preserves byte counts. A hash match does not establish that
    removing a file is safe or authorized; this scan is read-only; cleanup requires a separate confirmed request.
    """
    return max(file_count - 1, 0) * file_size_bytes


def get_duplicate_summary() -> DuplicateResponse:
    """Identify matching SHA-256/size groups and summarize potential savings.

    SHA-256 is calculated from actual upload bytes by the existing upload service.
    Matching sizes provide an extra consistency check.
    """
    records = find_duplicate_file_groups()
    groups = [DuplicateGroup(
        sha256=group.sha256, file_size_bytes=group.file_size_bytes,
        file_count=len(group.files), files=group.files,
        potential_savings_bytes=calculate_potential_savings(len(group.files), group.file_size_bytes),
    ) for group in records]
    return DuplicateResponse(
        summary=DuplicateSummary(
            duplicate_groups=len(groups),
            redundant_copies=sum(group.file_count - 1 for group in groups),
            potential_savings_bytes=sum(group.potential_savings_bytes for group in groups),
        ),
        groups=groups,
    )
