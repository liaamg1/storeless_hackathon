"""Real PostgreSQL tests use a disposable schema, never the public tables."""
import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pymupdf
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.rows import dict_row

from app.main import app
from app.services import document_jobs
from app.repositories import job_repository, upload_repository, visual_repository, presentation_repository, duplicate_repository, file_repository, search_repository, transcription_repository

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def disable_automatic_worker(monkeypatch):
    # Each test controls its own worker; never spawn a consumer of development jobs.
    monkeypatch.setenv("AUTO_START_TRANSCRIPTION_WORKER", "false")


@pytest.fixture
def pdf_bytes():
    def create(texts=("First page", "Second page")):
        with pymupdf.open() as document:
            for text in texts:
                page = document.new_page()
                if text:
                    page.insert_text((72, 72), text)
            return document.tobytes()
    return create


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    directory = tmp_path / "uploads"
    monkeypatch.setenv("UPLOAD_DIR", str(directory))
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "25000000")
    return directory


@pytest.fixture
def client(uploads):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def database(monkeypatch):
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set TEST_DATABASE_URL to run isolated PostgreSQL integration tests")
    schema = "restore_test_" + uuid4().hex
    with psycopg.connect(database_url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    def connect():
        return psycopg.connect(
            database_url, options=f"-csearch_path={schema}", row_factory=dict_row
        )
    try:
        with connect() as connection:
            # Start with the original schema and a legacy row to verify additive migration.
            original_schema = (ROOT / "database/01_schema.sql").read_text().split("BEGIN;")[0]
            connection.execute(original_schema)
            connection.execute(
                "INSERT INTO files (filename, size_bytes, sha256) VALUES ('legacy.pdf', 10, 'abc')"
            )
        migration = (ROOT / "database/migrations/001_pdf_extraction.sql").read_text()
        for _ in range(2):
            with connect() as connection:
                connection.execute(migration)
        search_migration = (ROOT / "database/migrations/002_document_search.sql").read_text()
        for _ in range(2):
            with connect() as connection:
                connection.execute(search_migration)
        video_migration = (ROOT / "database/migrations/004_video_transcription.sql").read_text()
        for _ in range(2):
            with connect() as connection:
                connection.execute(video_migration)
        transcript_search_migration = (ROOT / "database/migrations/005_transcript_search.sql").read_text()
        with connect() as connection:
            connection.execute(transcript_search_migration)
        with connect() as connection:
            connection.execute((ROOT / "database/migrations/006_slide_comparison.sql").read_text())
        for _ in range(2):
            with connect() as connection:
                connection.execute((ROOT / "database/migrations/007_video_visuals.sql").read_text())
        monkeypatch.setattr(visual_repository, "get_connection", connect)
        for _ in range(2):
            with connect() as connection:
                connection.execute((ROOT / "database/migrations/008_unified_upload.sql").read_text())
        for _ in range(2):
            with connect() as connection:
                connection.execute((ROOT / "database/migrations/009_duplicate_cleanup.sql").read_text())
        for _ in range(2):
            with connect() as connection:
                connection.execute((ROOT / "database/migrations/010_parallel_jobs.sql").read_text())
        monkeypatch.setattr(document_jobs,"get_connection",connect)
        monkeypatch.setattr(job_repository,"get_connection",connect)
        monkeypatch.setattr(job_repository,"new_connection",connect)
        monkeypatch.setattr(upload_repository, "get_connection", connect)
        monkeypatch.setattr(presentation_repository, "get_connection", connect)
        monkeypatch.setattr(transcription_repository, "get_connection", connect)
        monkeypatch.setattr(file_repository, "get_connection", connect)
        monkeypatch.setattr(search_repository, "get_connection", connect)
        monkeypatch.setattr(duplicate_repository, "get_connection", connect)
        yield connect
    finally:
        # Only the randomly named schema created by this fixture is ever dropped.
        with psycopg.connect(database_url, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
