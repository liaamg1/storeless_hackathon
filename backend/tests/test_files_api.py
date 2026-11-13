import hashlib
from pathlib import Path

import psycopg
import pytest

from app.services import file_service


def test_upload_and_retrieve_document(client, database, pdf_bytes, uploads):
    contents = pdf_bytes(("Network architecture", "", "Conclusion"))
    response = client.post("/files/upload", files={"file": ("network.pdf", contents, "application/pdf")})
    assert response.status_code == 201
    result = response.json()
    assert result["status"] == "completed"
    assert result["page_count"] == 3
    file_id = result["id"]
    with database() as connection:
        file = connection.execute("SELECT * FROM files WHERE id = %s", (file_id,)).fetchone()
        assert file["filename"] == "network.pdf"
        assert file["size_bytes"] == len(contents)
        assert file["sha256"] == hashlib.sha256(contents).hexdigest()
        assert Path(file["storage_path"]).read_bytes() == contents
        assert Path(file["storage_path"]).parent == uploads
        pages = connection.execute(
            "SELECT file_id FROM document_pages WHERE file_id = %s", (file_id,)
        ).fetchall()
        assert len(pages) == 3
    # A new GET reads persisted data rather than the original upload response.
    saved = client.get(f"/files/{file_id}/pages").json()
    assert saved["filename"] == "network.pdf"
    assert [p["page_number"] for p in saved["pages"]] == [1, 2, 3]
    assert [p["text"].strip() for p in saved["pages"]] == ["Network architecture", "", "Conclusion"]
    assert client.get("/files").status_code == 200
    assert any(f["id"] == file_id for f in client.get("/files").json())


@pytest.mark.parametrize("filename,contents,status", [
    ("notes.txt", b"plain text", 415),
    ("fake.pdf", b"plain text", 415),
    ("empty.pdf", b"", 400),
    ("broken.pdf", b"%PDF-1.7\ncorrupted", 400),
])
def test_invalid_uploads(client, uploads, filename, contents, status):
    response = client.post("/files/upload", files={"file": (filename, contents, "application/pdf")})
    assert response.status_code == status
    assert isinstance(response.json()["detail"], str)
    assert not list(uploads.glob("*"))


def test_oversized_upload(client, monkeypatch, uploads, pdf_bytes):
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "50")
    response = client.post("/files/upload", files={"file": ("large.pdf", pdf_bytes())})
    assert response.status_code == 413
    assert not list(uploads.glob("*"))


def test_storage_failure(client, uploads, pdf_bytes):
    uploads.write_text("This path is a file, not a directory")
    response = client.post("/files/upload", files={"file": ("document.pdf", pdf_bytes())})
    assert response.status_code == 500
    assert uploads.read_text() == "This path is a file, not a directory"


def test_database_failure_removes_upload(client, monkeypatch, uploads, pdf_bytes):
    def fail(*args):
        raise psycopg.OperationalError("Database unavailable")
    monkeypatch.setattr(file_service, "create_document", fail)
    response = client.post("/files/upload", files={"file": ("document.pdf", pdf_bytes())})
    assert response.status_code == 500
    assert not list(uploads.glob("*"))
    assert "Database unavailable" not in response.text


def test_unknown_and_legacy_documents(client, database):
    assert client.get("/files/999999/pages").status_code == 404
    files = client.get("/files").json()
    assert files[0]["filename"] == "legacy.pdf"
    assert "uploaded_at" in files[0]
    saved = client.get(f"/files/{files[0]['id']}/pages").json()
    assert saved["pages"] == []
    assert saved["status"] == "not_processed"


def test_unique_paths_and_safe_filename(client, database, pdf_bytes, uploads):
    for _ in range(2):
        response = client.post("/files/upload", files={"file": ("../../escape.pdf", pdf_bytes())})
        assert response.status_code == 201
        assert response.json()["filename"] == "escape.pdf"
    assert len(list(uploads.glob("*.pdf"))) == 2


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_password_protected_upload(client, uploads, tmp_path):
    import pymupdf
    path = tmp_path / "encrypted.pdf"
    with pymupdf.open() as document:
        document.new_page()
        document.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256,
                      owner_pw="owner", user_pw="secret")
    response = client.post("/files/upload", files={"file": ("encrypted.pdf", path.read_bytes())})
    assert response.status_code == 400
    assert "Password-protected" in response.json()["detail"]
    assert not list(uploads.glob("*"))


def test_collision_does_not_remove_existing_file(client, monkeypatch, uploads, pdf_bytes):
    from types import SimpleNamespace
    monkeypatch.setattr(file_service, "uuid4", lambda: SimpleNamespace(hex="existing"))
    uploads.mkdir()
    path = uploads / "existing.pdf"
    path.write_bytes(b"existing document")
    response = client.post("/files/upload", files={"file": ("document.pdf", pdf_bytes())})
    assert response.status_code == 500
    assert path.read_bytes() == b"existing document"


def test_failed_page_insert_rolls_back_and_removes_pdf(client, database, monkeypatch, uploads, pdf_bytes):
    from app.processors.pdf_processor import ExtractedPage
    monkeypatch.setattr(file_service, "extract_pdf_pages", lambda _: [
        ExtractedPage(1, "sensitive text"), ExtractedPage(1, "duplicate"),
    ])
    response = client.post("/files/upload", files={"file": ("document.pdf", pdf_bytes())})
    assert response.status_code == 500
    assert not list(uploads.glob("*"))
    with database() as connection:
        assert connection.execute("SELECT count(*) AS count FROM files").fetchone()["count"] == 1
        assert connection.execute("SELECT count(*) AS count FROM document_pages").fetchone()["count"] == 0


def test_image_only_upload_is_successful(client, database, pdf_bytes):
    response = client.post("/files/upload", files={"file": ("scan.pdf", pdf_bytes(("",)))})
    assert response.status_code == 201
    document = client.get(f"/files/{response.json()['id']}/pages").json()
    assert document["status"] == "completed"
    assert document["pages"] == [{"page_number": 1, "text": ""}]
