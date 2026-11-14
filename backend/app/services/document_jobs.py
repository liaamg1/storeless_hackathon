"""Incremental PDF text persistence and inexpensive queued duplicate checks."""

import logging

from app.core.database import get_connection
from app.processors.pdf_processor import iter_pdf_pages
from app.repositories.job_repository import progress
from app.repositories.transcription_repository import fail_job, update_job_step
from app.services.duplicate_service import get_duplicate_summary

logger = logging.getLogger(__name__)


def process_document_job(job) -> None:
    try:
        if job.job_type == 'pdf_text':
            # Pages are generated one at a time. One transaction prevents partial
            # documents becoming searchable if parsing or persistence fails.
            with get_connection() as connection:
                with connection.transaction():
                    with connection.cursor() as cursor:
                        for page in iter_pdf_pages(
                            job.storage_path,
                            on_progress=lambda done, total: progress(job.job_id, done, total, 'pages'),
                        ):
                            cursor.execute(
                                '''INSERT INTO document_pages(file_id,page_number,extracted_text)
                                VALUES(%s,%s,%s) ON CONFLICT(file_id,page_number) DO NOTHING''',
                                (job.file_id, page.page_number, page.text),
                            )
        else:
            get_duplicate_summary()
        update_job_step(job.job_id, 'saving_text' if job.job_type == 'pdf_text' else 'duplicate_check')
        with get_connection() as connection:
            connection.execute(
                "UPDATE processing_jobs SET status='completed',current_step='completed',completed_at=NOW(),error_message=NULL WHERE id=%s AND status='processing'",
                (job.job_id,),
            )
    except Exception as exc:
        logger.error("document_processing_failed job_id=%s error_type=%s", job.job_id, type(exc).__name__)
        from app.processors.pdf_processor import InvalidPdfError

        fail_job(
            job.job_id,
            (
                str(exc)
                if isinstance(exc, InvalidPdfError)
                else 'Document processing failed. The original is preserved; retry this file.'
            ),
        )
