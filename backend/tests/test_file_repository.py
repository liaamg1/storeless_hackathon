from pathlib import Path

import psycopg
import pytest

from app.processors.pdf_processor import ExtractedPage
from app.repositories.file_repository import create_document, get_document_pages


def test_page_ordering(database):
    result = create_document("ordered.pdf", 10, "hash", Path("/tmp/test.pdf"), [
        ExtractedPage(3, "third"), ExtractedPage(1, "first"), ExtractedPage(2, ""),
    ])
    document = get_document_pages(result.id)
    assert [page.page_number for page in document.pages] == [1, 2, 3]
    assert document.pages[1].text == ""


def test_transaction_rolls_back(database):
    with database() as connection:
        before = connection.execute("SELECT count(*) AS count FROM files").fetchone()["count"]
    # The duplicate page number fails after metadata and the first page were inserted.
    with pytest.raises(psycopg.errors.UniqueViolation):
        create_document("rollback.pdf", 10, "hash", Path("/tmp/test.pdf"), [
            ExtractedPage(1, "first"), ExtractedPage(1, "duplicate"),
        ])
    with database() as connection:
        assert connection.execute("SELECT count(*) AS count FROM files").fetchone()["count"] == before
        assert connection.execute("SELECT count(*) AS count FROM document_pages").fetchone()["count"] == 0


def test_migration_preserves_legacy_data(database):
    with database() as connection:
        row = connection.execute("SELECT filename, storage_path FROM files").fetchone()
        assert row == {"filename": "legacy.pdf", "storage_path": None}


def test_fresh_install_schema(database):
    from conftest import ROOT
    with database() as connection:
        connection.execute((ROOT / "database/01_schema.sql").read_text())
        assert connection.execute("SELECT count(*) AS count FROM files").fetchone()["count"] == 1
