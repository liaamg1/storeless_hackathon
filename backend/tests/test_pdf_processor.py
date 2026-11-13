import pymupdf
import pytest

from app.processors.pdf_processor import InvalidPdfError, extract_pdf_pages


@pytest.mark.parametrize("texts", [("Hello ReStore",), ("First", "Second"), ("Text", "")])
def test_extract_pages(tmp_path, pdf_bytes, texts):
    path = tmp_path / "document.pdf"
    path.write_bytes(pdf_bytes(texts))
    pages = extract_pdf_pages(path)
    assert [page.page_number for page in pages] == list(range(1, len(texts) + 1))
    assert [page.text.strip() for page in pages] == list(texts)


@pytest.mark.parametrize("contents", [b"invalid", b"%PDF-1.7\ncorrupted", b""])
def test_invalid_pdf(tmp_path, contents):
    path = tmp_path / "broken.pdf"
    path.write_bytes(contents)
    with pytest.raises(InvalidPdfError):
        extract_pdf_pages(path)


def test_password_protected_pdf(tmp_path):
    path = tmp_path / "encrypted.pdf"
    with pymupdf.open() as document:
        document.new_page()
        document.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256,
                      owner_pw="owner", user_pw="secret")
    with pytest.raises(InvalidPdfError, match="Password-protected"):
        extract_pdf_pages(path)
