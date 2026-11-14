"""Duplicate scans use real PostgreSQL in disposable schemas, never public tables."""
import hashlib
from datetime import datetime, timezone

import psycopg
import pytest

from app.repositories import duplicate_repository
from app.services.duplicate_service import calculate_potential_savings


@pytest.fixture
def duplicate_files(database):
    # The database fixture owns a fresh restore_test_* schema for this test only.
    with database() as connection:
        connection.execute("DELETE FROM files")

    def store(filename, content=b"identical bytes", *, size=None, digest=None,
              uploaded_at="2026-11-11T12:00:00Z", storage_path="/tmp/duplicate-test.pdf"):
        actual_digest = hashlib.sha256(content).hexdigest() if digest is None else digest
        with database() as connection:
            return connection.execute(
                """INSERT INTO files (filename, size_bytes, sha256, uploaded_at, storage_path)
                   VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                (filename, len(content) if size is None else size, actual_digest, uploaded_at, storage_path),
            ).fetchone()["id"]
    return store


def scan(client):
    response = client.get("/duplicates")
    assert response.status_code == 200, response.text
    return response.json()


def test_no_files(client, duplicate_files):
    assert scan(client) == {
        "summary": {"duplicate_groups": 0, "redundant_copies": 0,
                    "potential_savings_bytes": 0},
        "groups": [],
    }


def test_only_unique_files(client, duplicate_files):
    duplicate_files("one.pdf", b"one")
    duplicate_files("two.pdf", b"two")
    assert scan(client)["groups"] == []


@pytest.mark.parametrize("file_count", [2, 3])
def test_identical_files_with_different_names(client, duplicate_files, file_count):
    content = b"same real content"
    ids = [duplicate_files(f"copy-{index}.pdf", content) for index in range(file_count)]
    result = scan(client)
    assert result["summary"] == {
        "duplicate_groups": 1, "redundant_copies": file_count - 1,
        "potential_savings_bytes": (file_count - 1) * len(content),
    }
    group = result["groups"][0]
    assert group["sha256"] == hashlib.sha256(content).hexdigest()
    assert group["file_size_bytes"] == len(content)
    assert group["file_count"] == file_count
    assert group["potential_savings_bytes"] == (file_count - 1) * len(content)
    assert [file["id"] for file in group["files"]] == ids
    assert set(group["files"][0]) == {"id", "filename", "size_bytes", "uploaded_at", "completed_operations"}
    assert "storage_path" not in group["files"][0]


def test_multiple_groups_and_unique_files(client, duplicate_files):
    for number in range(2):
        duplicate_files(f"group-one-{number}.pdf", b"a" * 10)
    for number in range(3):
        duplicate_files(f"group-two-{number}.pdf", b"b" * 20)
    duplicate_files("unique.pdf", b"unique")
    result = scan(client)
    assert result["summary"] == {
        "duplicate_groups": 2, "redundant_copies": 3,
        "potential_savings_bytes": 50,
    }
    assert sorted(group["file_count"] for group in result["groups"]) == [2, 3]
    assert all(file["filename"] != "unique.pdf" for group in result["groups"] for file in group["files"])


def test_same_filename_different_content_is_unique(client, duplicate_files):
    duplicate_files("same-name.pdf", b"first")
    duplicate_files("same-name.pdf", b"other")
    assert scan(client)["groups"] == []


def test_matching_hash_different_sizes(client, duplicate_files):
    duplicate_files("one.pdf", size=10)
    duplicate_files("two.pdf", size=11)
    assert scan(client)["groups"] == []
    duplicate_files("three.pdf", size=10)
    group = scan(client)["groups"][0]
    assert group["file_size_bytes"] == 10
    assert {file["filename"] for file in group["files"]} == {"one.pdf", "three.pdf"}


@pytest.mark.parametrize("digest", ["", "unknown", "pending", "a" * 63, "a" * 65,
                                       "g" * 64, "0" * 64, "a" * 64, "f" * 64,
                                       " " + "a" * 64, "a" * 64 + "\n"])
def test_invalid_and_placeholder_hashes_are_excluded(client, duplicate_files, digest):
    duplicate_files("first.pdf", digest=digest)
    duplicate_files("second.pdf", digest=digest)
    assert scan(client)["groups"] == []


def test_missing_hashes_are_excluded(client, database, duplicate_files):
    # Simulate older imported metadata; production's NOT NULL constraint stays intact.
    with database() as connection:
        connection.execute("ALTER TABLE files ALTER COLUMN sha256 DROP NOT NULL")
        connection.execute(
            "INSERT INTO files (filename, size_bytes, sha256) VALUES ('one.pdf', 1, NULL), ('two.pdf', 1, NULL)"
        )
    assert scan(client)["groups"] == []


def test_hex_case_is_normalized(client, duplicate_files):
    digest = hashlib.sha256(b"case").hexdigest()
    duplicate_files("first.pdf", digest=digest)
    duplicate_files("second.pdf", digest=digest.upper())
    group = scan(client)["groups"][0]
    assert group["sha256"] == digest
    assert group["file_count"] == 2


def test_removing_samples_preserves_real_uploads(client, database, duplicate_files):
    from conftest import ROOT
    duplicate_files("training.pdf", digest="a" * 64, size=12000000, storage_path=None)
    duplicate_files("training (1).pdf", digest="a" * 64, size=12000000, storage_path=None)
    duplicate_files("architecture.pdf", digest="b" * 64, size=8000000, storage_path=None)
    real_id = duplicate_files("training.pdf", b"actual uploaded bytes")
    stored_id = duplicate_files("training.pdf", digest="a" * 64, size=12000000)
    extracted_id = duplicate_files("architecture.pdf", digest="b" * 64, size=8000000, storage_path=None)
    with database() as connection:
        connection.execute(
            "INSERT INTO document_pages (file_id, page_number, extracted_text) VALUES (%s, 1, 'Preserve this document')",
            (extracted_id,),
        )
    migration = (ROOT / "database/migrations/003_remove_sample_data.sql").read_text()
    for _ in range(2):
        with database() as connection:
            connection.execute(migration)
    with database() as connection:
        files = connection.execute("SELECT id FROM files ORDER BY id").fetchall()
        assert [file["id"] for file in files] == [real_id, stored_id, extracted_id]
        assert connection.execute("SELECT count(*) AS count FROM document_pages").fetchone()["count"] == 1
    assert scan(client)["groups"] == []


def test_consistent_group_and_file_order(client, duplicate_files):
    first = duplicate_files("late.pdf", uploaded_at="2026-11-11T14:00:00Z")
    second = duplicate_files("early.pdf", uploaded_at="2026-11-11T10:00:00Z")
    third = duplicate_files("same-date.pdf", uploaded_at="2026-11-11T10:00:00Z")
    fourth = duplicate_files("unknown-date.pdf", uploaded_at=None)
    duplicate_files("other-one.pdf", b"different")
    duplicate_files("other-two.pdf", b"different")
    result = scan(client)
    assert [group["sha256"] for group in result["groups"]] == sorted(group["sha256"] for group in result["groups"])
    group = next(group for group in result["groups"] if group["file_count"] == 4)
    assert [file["id"] for file in group["files"]] == [second, third, first, fourth]
    assert group["files"][-1]["uploaded_at"] is None
    assert datetime.fromisoformat(group["files"][0]["uploaded_at"].replace("Z", "+00:00")) == datetime(2026, 11, 11, 10, tzinfo=timezone.utc)
    assert scan(client) == result


def test_zero_size_and_invalid_negative_sizes(client, duplicate_files):
    duplicate_files("empty-one.pdf", b"")
    duplicate_files("empty-two.pdf", b"")
    duplicate_files("negative-one.pdf", b"negative", size=-1)
    duplicate_files("negative-two.pdf", b"negative", size=-1)
    result = scan(client)
    assert result["summary"]["duplicate_groups"] == 1
    assert result["summary"]["potential_savings_bytes"] == 0


@pytest.mark.parametrize("count,size,expected", [(0, 10, 0), (1, 10, 0), (2, 10, 10),
                                                 (3, 10000000, 20000000), (2, 0, 0),
                                                 (3, 9007199254740993, 18014398509481986)])
def test_integer_savings(count, size, expected):
    result = calculate_potential_savings(count, size)
    assert result == expected
    assert isinstance(result, int)


def test_scan_preserves_metadata_and_original_files(client, database, duplicate_files, tmp_path, monkeypatch):
    from app.services import file_service
    def fail(*args):
        raise AssertionError("A scan must not process or hash PDFs")
    monkeypatch.setattr(file_service, "extract_pdf_pages", fail)
    monkeypatch.setattr(file_service, "save_uploaded_file", fail)
    content = b"original bytes"
    paths = [tmp_path / "first.pdf", tmp_path / "second.pdf"]
    for path in paths:
        path.write_bytes(content)
        duplicate_files(path.name, content, storage_path=str(path))
    with database() as connection:
        before = connection.execute("SELECT * FROM files ORDER BY id").fetchall()
        pages_before = connection.execute("SELECT * FROM document_pages ORDER BY id").fetchall()
    assert scan(client)["summary"]["duplicate_groups"] == 1
    with database() as connection:
        assert connection.execute("SELECT * FROM files ORDER BY id").fetchall() == before
        assert connection.execute("SELECT * FROM document_pages ORDER BY id").fetchall() == pages_before
    assert [path.read_bytes() for path in paths] == [content, content]


def test_uploaded_pdf_duplicates_use_actual_hashes(client, database, pdf_bytes):
    contents = pdf_bytes()
    ids = []
    for filename in ["original.pdf", "renamed.pdf"]:
        response = client.post("/files/upload", files={"file": (filename, contents, "application/pdf")})
        assert response.status_code == 201
        ids.append(response.json()["id"])
    group = scan(client)["groups"][0]
    assert group["sha256"] == hashlib.sha256(contents).hexdigest()
    assert {file["id"] for file in group["files"]} == set(ids)
    assert group["potential_savings_bytes"] == len(contents)


def test_database_errors_are_private(client, monkeypatch, caplog):
    def fail():
        raise psycopg.OperationalError("postgresql://secret credentials; raw SQL")
    monkeypatch.setattr(duplicate_repository, "get_connection", fail)
    response = client.get("/duplicates")
    assert response.status_code == 500
    assert response.json() == {"detail": "Duplicate scan is unavailable. Please try again."}
    assert "secret credentials" not in response.text + caplog.text
    assert "raw SQL" not in response.text + caplog.text
    assert "OperationalError" in caplog.text
