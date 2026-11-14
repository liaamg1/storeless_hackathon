"""PDF parsing only: no HTTP, storage management, or database dependencies."""

from dataclasses import dataclass
from pathlib import Path

import pymupdf


class InvalidPdfError(ValueError):
    """The document cannot be read without repair or a password."""


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int
    text: str


def iter_pdf_pages(file_path: Path, *, on_progress=None):
    """Extract selectable text page by page, preserving empty pages.

    Image-only pages return empty text because this feature does not perform OCR.
    The context manager closes the document even if page extraction fails.
    """
    try:
        with pymupdf.open(file_path) as document:
            if not document.is_pdf:
                raise InvalidPdfError("The uploaded document is not a PDF.")
            if document.needs_pass:
                raise InvalidPdfError("Password-protected PDFs cannot be extracted.")
            if document.is_repaired or document.page_count == 0:
                raise InvalidPdfError("The PDF is corrupted or contains no pages.")
            if on_progress:
                on_progress(0, document.page_count)
            for index, page in enumerate(document):
                yield ExtractedPage(index + 1, page.get_text("text"))
                if on_progress:
                    on_progress(index + 1, document.page_count)
    except (RuntimeError, ValueError) as exc:
        if isinstance(exc, InvalidPdfError):
            raise
        raise InvalidPdfError("The PDF is corrupted or unreadable.") from exc


def validate_pdf(file_path: Path) -> None:
    # Opening/validating the header and page tree does not extract page content.
    # Validation shares the parser's checks, without retaining extracted text.
    try:
        with pymupdf.open(file_path) as document:
            if not document.is_pdf or document.needs_pass or document.is_repaired or document.page_count == 0:
                raise InvalidPdfError("Upload an intact, unencrypted PDF containing pages.")
    except (RuntimeError, ValueError) as exc:
        raise InvalidPdfError("The PDF is corrupted, protected or unreadable.") from exc


def extract_pdf_pages(file_path: Path) -> list[ExtractedPage]:
    return list(iter_pdf_pages(file_path))
