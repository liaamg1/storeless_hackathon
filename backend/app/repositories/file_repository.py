"""SQL and transaction boundaries for files and their extracted pages."""

from pathlib import Path
from psycopg.types.json import Jsonb

from app.core.database import get_connection
from app.processors.pdf_processor import ExtractedPage
from app.schemas.file import DocumentDetails, FileRecord, UploadResult


def list_files() -> list[FileRecord]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT id, filename, size_bytes, sha256, uploaded_at FROM files WHERE original_removed_at IS NULL ORDER BY id"
        ).fetchall()
    return [FileRecord(**row) for row in rows]


def create_document(
    filename: str,
    size_bytes: int,
    sha256: str,
    storage_path: Path,
    pages: list[ExtractedPage],
    *,
    processing_options: list[str] | None = None,
    analyze_slides: bool = True,
    background_text: bool = False,
) -> UploadResult:
    """Commit metadata and all pages together, or roll back both on failure."""
    with get_connection() as connection:
        with connection.transaction():
            row = connection.execute(
                """INSERT INTO files (filename, size_bytes, sha256, storage_path, processing_options)
                   VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                (
                    filename,
                    size_bytes,
                    sha256,
                    str(storage_path),
                    Jsonb(processing_options) if processing_options is not None else None,
                ),
            ).fetchone()
            file_id = row["id"]
            with connection.cursor() as cursor:
                cursor.executemany(
                    """INSERT INTO document_pages (file_id, page_number, extracted_text)
                       VALUES (%s, %s, %s)""",
                    [(file_id, page.page_number, page.text) for page in pages],
                )
            if background_text:
                connection.execute(
                    "INSERT INTO processing_jobs(file_id,job_type) VALUES(%s,'pdf_text')", (file_id,)
                )
            if analyze_slides:
                connection.execute(
                    "INSERT INTO processing_jobs (file_id, job_type) VALUES (%s, 'presentation_analysis')",
                    (file_id,),
                )
    return UploadResult(id=file_id, filename=filename, size_bytes=size_bytes, page_count=len(pages))


def get_document_pages(file_id: int) -> DocumentDetails | None:
    with get_connection() as connection:
        file = connection.execute(
            "SELECT filename, size_bytes FROM files WHERE id = %s", (file_id,)
        ).fetchone()
        if file is None:
            return None
        pages = connection.execute(
            """SELECT page_number, extracted_text AS text FROM document_pages
               WHERE file_id = %s ORDER BY page_number""",
            (file_id,),
        ).fetchall()
    return DocumentDetails(
        file_id=file_id,
        filename=file["filename"],
        size_bytes=file["size_bytes"],
        page_count=len(pages),
        status="completed" if pages else "not_processed",
        pages=pages,
    )


def get_storage_source(file_id: int) -> dict | None:
    """Retrieve the actual upload byte count and its existing processing state."""
    with get_connection() as connection:
        return connection.execute(
            """SELECT f.id AS file_id, f.filename, f.size_bytes, f.file_type, f.duplicate_of, f.original_removed_at,
                      j.status AS job_status
               FROM files f LEFT JOIN processing_jobs j
                 ON j.file_id = f.id AND j.job_type = 'video_transcription'
               WHERE f.id = %s""",
            (file_id,),
        ).fetchone()
