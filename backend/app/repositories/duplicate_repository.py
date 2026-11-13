"""Read duplicate candidates in one query without opening uploaded files."""
from dataclasses import dataclass

from app.core.database import get_connection
from app.schemas.duplicate import DuplicateFile


@dataclass(frozen=True)
class DuplicateGroupRecords:
    sha256: str
    file_size_bytes: int
    files: list[DuplicateFile]


def find_duplicate_file_groups() -> list[DuplicateGroupRecords]:
    """Group distinct file rows by normalized SHA-256 and size.

    Repeated-character hashes are treated as placeholders, not evidence of
    identical content. A scan trusts metadata and never verifies filesystem bytes.
    """
    with get_connection() as connection:
        rows = connection.execute(
            """
            WITH valid_files AS (
                SELECT id, filename, size_bytes, lower(sha256) AS sha256, uploaded_at
                FROM files
                WHERE sha256 ~* '^[0-9a-f]{64}$' AND size_bytes >= 0
            ), eligible_files AS (
                SELECT * FROM valid_files
                WHERE sha256 <> repeat(left(sha256, 1), 64)
            )
            SELECT sha256, size_bytes AS file_size_bytes,
                   jsonb_agg(jsonb_build_object(
                       'id', id, 'filename', filename, 'size_bytes', size_bytes,
                       'uploaded_at', uploaded_at
                   ) ORDER BY uploaded_at ASC NULLS LAST, id) AS files
            FROM eligible_files
            GROUP BY sha256, size_bytes
            HAVING count(*) > 1
            ORDER BY sha256, size_bytes
            """
        ).fetchall()
    return [DuplicateGroupRecords(
        sha256=row["sha256"], file_size_bytes=row["file_size_bytes"],
        files=[DuplicateFile(**file) for file in row["files"]],
    ) for row in rows]
