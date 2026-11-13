"""Search semantics are tested against PostgreSQL, not simulated substring logic."""
from pathlib import Path

import psycopg
import pytest

from app.processors.pdf_processor import ExtractedPage
from app.repositories.file_repository import create_document
from app.services import search_service
from app.services.search_service import InvalidSearchQuery, search_document_pages


@pytest.fixture
def documents(database):
    def store(filename, texts):
        return create_document(filename, 100, "test-hash", Path("/tmp/search-test.pdf"), [
            ExtractedPage(number, text) for number, text in enumerate(texts, 1)
        ])
    network = store("network.pdf", [
        "Network architecture connects components. Network architecture defines topology.",
        "Network security uses encryption to protect communication.",
        "Architecture describes distributed components in a network.",
        "",
    ])
    systems = store("systems.pdf", [
        "A network architecture overview for engineers.",
        "Storage systems retain files on disk.",
    ])
    return network, systems, store


def search(client, query, limit=None):
    parameters = {"q": query}
    if limit is not None:
        parameters["limit"] = limit
    response = client.get("/search", params=parameters)
    assert response.status_code == 200, response.text
    return response.json()


def test_single_matching_page(client, documents):
    network, _, _ = documents
    result = search(client, "encryption")
    assert result["returned_count"] == 1
    page = result["results"][0]
    assert page["file_id"] == network.id
    assert page["filename"] == "network.pdf"
    assert page["page_number"] == 2
    assert "encryption" in page["snippet"]
    assert page["relevance"] > 0


def test_multiple_documents_and_pages(client, documents):
    network, systems, _ = documents
    result = search(client, "network architecture")
    assert {(page["file_id"], page["page_number"]) for page in result["results"]} == {
        (network.id, 1), (network.id, 3), (systems.id, 1),
    }
    assert result["returned_count"] == 3


@pytest.mark.parametrize("query", ["NETWORK ARCHITECTURE", "  network \t\n architecture  "])
def test_case_and_whitespace(client, documents, query):
    assert search(client, query)["results"] == search(client, "network architecture")["results"]
    assert search(client, query)["query"].lower() == "network architecture"


def test_phrase_query(client, documents):
    network, systems, _ = documents
    result = search(client, '"network architecture"')
    assert {(page["file_id"], page["page_number"]) for page in result["results"]} == {
        (network.id, 1), (systems.id, 1),
    }


def test_exclusions_and_or(client, documents):
    network, systems, _ = documents
    excluded = search(client, "network -security")
    assert all(page["page_number"] != 2 for page in excluded["results"])
    assert excluded["returned_count"] == 3
    alternatives = search(client, "encryption OR storage")
    assert {(page["file_id"], page["page_number"]) for page in alternatives["results"]} == {
        (network.id, 2), (systems.id, 2),
    }


def test_no_matches(client, documents):
    assert search(client, "nonexistentword") == {
        "query": "nonexistentword", "returned_count": 0, "results": [],
    }


def test_before_any_documents_exist(client, database):
    assert search(client, "network")["results"] == []


@pytest.mark.parametrize("query", ["&|!()", '"', "network & (architecture)!", "'; DROP TABLE files; --"])
def test_special_characters_are_safe(client, documents, database, query):
    result = search(client, query)
    assert result["returned_count"] == len(result["results"])
    with database() as connection:
        assert connection.execute("SELECT count(*) AS count FROM files").fetchone()["count"] == 3


def test_result_limit_and_count(client, documents):
    result = search(client, "network", limit=1)
    assert len(result["results"]) == result["returned_count"] == 1
    assert "total" not in result


def test_default_and_maximum_limits(client, documents):
    _, _, store = documents
    store("many.pdf", ["uniquetoken" for _ in range(105)])
    assert search(client, "uniquetoken")["returned_count"] == 20
    assert search(client, "uniquetoken", limit=100)["returned_count"] == 100


def test_stable_ordering_for_equal_ranks(client, documents):
    _, _, store = documents
    first = store("first.pdf", ["equalrank", "equalrank"])
    second = store("second.pdf", ["equalrank"])
    expected = [(first.id, 1), (first.id, 2), (second.id, 1)]
    for _ in range(2):
        result = search(client, "equalrank")
        assert [(page["file_id"], page["page_number"]) for page in result["results"]] == expected


def test_cover_density_ranking(client, documents):
    network, _, _ = documents
    results = search(client, "network architecture")["results"]
    assert (results[0]["file_id"], results[0]["page_number"]) == (network.id, 1)
    assert results[0]["relevance"] > results[-1]["relevance"]
    assert [page["relevance"] for page in results] == sorted(
        [page["relevance"] for page in results], reverse=True
    )


def test_plain_short_snippets(client, documents):
    _, _, store = documents
    store("long.pdf", ["network " + "x" * 700])
    results = search(client, "network")["results"]
    assert all(len(page["snippet"]) <= 500 for page in results)
    assert all("<b>" not in page["snippet"] for page in results)
    assert all("\n" not in page["snippet"] for page in results)


@pytest.mark.parametrize("parameters", [
    {}, {"q": ""}, {"q": " \t\n "}, {"q": "x" * 201}, {"q": "network\x00"},
    {"q": "network", "limit": 0}, {"q": "network", "limit": -1},
    {"q": "network", "limit": 101}, {"q": "network", "limit": "invalid"},
])
def test_invalid_api_parameters(client, parameters):
    assert client.get("/search", params=parameters).status_code == 422


def test_normalization_and_response_semantics(monkeypatch):
    calls = []
    def get_matches(query, limit):
        calls.append((query, limit))
        return []
    monkeypatch.setattr(search_service, "get_matching_pages", get_matches)
    response = search_document_pages('  "network   architecture"  -security ', 7)
    assert calls == [('"network architecture" -security', 7)]
    assert response.query == '"network architecture" -security'
    assert response.returned_count == 0


@pytest.mark.parametrize("query,limit", [(" ", 20), ("x" * 201, 20), ("x", 0), ("x", 101)])
def test_service_validation(query, limit):
    with pytest.raises(InvalidSearchQuery):
        search_document_pages(query, limit)


def test_database_failure_is_private(client, monkeypatch, caplog):
    def fail(query, limit):
        raise psycopg.OperationalError("postgresql://secret credentials; SQL; document contents")
    monkeypatch.setattr(search_service, "get_matching_pages", fail)
    response = client.get("/search", params={"q": "network"})
    assert response.status_code == 500
    assert response.json()["detail"] == "Document search is unavailable. Please try again."
    assert "secret credentials" not in response.text + caplog.text
    assert "OperationalError" in caplog.text


def test_search_result_opens_original_page(client, documents):
    page = search(client, "encryption")["results"][0]
    document = client.get(f"/files/{page['file_id']}/pages").json()
    selected = next(p for p in document["pages"] if p["page_number"] == page["page_number"])
    assert "encryption" in selected["text"]


def test_new_upload_is_searchable_without_reprocessing(client, database, pdf_bytes, monkeypatch):
    response = client.post("/files/upload", files={"file": (
        "uploaded.pdf", pdf_bytes(("New searchable terminology",)), "application/pdf",
    )})
    assert response.status_code == 201
    from app.services import file_service
    def fail(*args):
        raise AssertionError("Search must not open or reprocess PDFs")
    monkeypatch.setattr(file_service, "extract_pdf_pages", fail)
    result = search(client, "terminology")["results"][0]
    assert result["file_id"] == response.json()["id"]
    assert result["filename"] == "uploaded.pdf"


def test_search_migration_is_repeatable_and_preserves_pages(database, documents):
    from conftest import ROOT
    migration = (ROOT / "database/migrations/002_document_search.sql").read_text()
    with database() as connection:
        before = connection.execute("SELECT * FROM document_pages ORDER BY id").fetchall()
        connection.execute("DROP INDEX idx_document_pages_fts")
    for _ in range(2):
        with database() as connection:
            connection.execute(migration)
    with database() as connection:
        assert connection.execute("SELECT * FROM document_pages ORDER BY id").fetchall() == before
        indexes = connection.execute(
            "SELECT indexdef FROM pg_indexes WHERE schemaname = current_schema() AND indexname = %s",
            ("idx_document_pages_fts",),
        ).fetchall()
        assert len(indexes) == 1
        assert "USING gin" in indexes[0]["indexdef"]
        assert "'simple'::regconfig" in indexes[0]["indexdef"]
        connection.execute("SET LOCAL enable_seqscan = off")
        plan = connection.execute(
            "EXPLAIN SELECT id FROM document_pages "
            "WHERE to_tsvector('simple', extracted_text) @@ websearch_to_tsquery('simple', %s)",
            ("network",),
        ).fetchall()
        assert "idx_document_pages_fts" in str(plan)
