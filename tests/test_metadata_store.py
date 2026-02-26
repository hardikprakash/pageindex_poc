"""
Tests for the local metadata store (SQLite).
"""

import os
import sys
import tempfile
import pytest

# Ensure project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Override DB path before import
_TMP_DB = tempfile.mktemp(suffix=".db")
os.environ["METADATA_DB_PATH"] = _TMP_DB

import metadata_store  # noqa: E402  — must be after env override


@pytest.fixture(autouse=True)
def _clean_db():
    """Reset the database before each test."""
    if os.path.exists(_TMP_DB):
        os.remove(_TMP_DB)
    # Force re-init by re-importing won't work; just recreate table
    conn = metadata_store._connect()
    conn.execute("DELETE FROM documents")
    conn.commit()
    conn.close()
    yield
    if os.path.exists(_TMP_DB):
        os.remove(_TMP_DB)


def test_upsert_and_get():
    metadata_store.upsert_document(
        doc_id="pi-001",
        filename="AAPL_2023.pdf",
        company="Apple Inc.",
        ticker="AAPL",
        fiscal_year=2023,
        doc_type="10-K",
        status="processing",
    )
    doc = metadata_store.get_document("pi-001")
    assert doc is not None
    assert doc["company"] == "Apple Inc."
    assert doc["ticker"] == "AAPL"
    assert doc["fiscal_year"] == 2023
    assert doc["status"] == "processing"


def test_upsert_overwrites():
    metadata_store.upsert_document(
        doc_id="pi-002", filename="A.pdf", company="X", ticker="X", fiscal_year=2020
    )
    metadata_store.upsert_document(
        doc_id="pi-002", filename="A.pdf", company="Y", ticker="Y", fiscal_year=2021
    )
    doc = metadata_store.get_document("pi-002")
    assert doc["company"] == "Y"
    assert doc["fiscal_year"] == 2021


def test_update_status():
    metadata_store.upsert_document(
        doc_id="pi-003", filename="B.pdf", company="Z", ticker="Z",
        fiscal_year=2022, status="processing",
    )
    metadata_store.update_status("pi-003", "completed", page_count=42)
    doc = metadata_store.get_document("pi-003")
    assert doc["status"] == "completed"
    assert doc["page_count"] == 42


def test_list_documents():
    metadata_store.upsert_document(
        doc_id="pi-a", filename="a.pdf", company="Alpha", ticker="A", fiscal_year=2020
    )
    metadata_store.upsert_document(
        doc_id="pi-b", filename="b.pdf", company="Beta", ticker="B", fiscal_year=2021
    )
    docs = metadata_store.list_documents()
    assert len(docs) == 2
    assert docs[0]["company"] == "Alpha"  # sorted by company


def test_delete_document():
    metadata_store.upsert_document(
        doc_id="pi-del", filename="d.pdf", company="Del", ticker="D", fiscal_year=2023
    )
    assert metadata_store.delete_document("pi-del") is True
    assert metadata_store.get_document("pi-del") is None
    assert metadata_store.delete_document("nonexistent") is False


def test_get_companies_and_years():
    metadata_store.upsert_document(
        doc_id="pi-c1", filename="c1.pdf", company="Acme", ticker="AC", fiscal_year=2021
    )
    metadata_store.upsert_document(
        doc_id="pi-c2", filename="c2.pdf", company="Beta", ticker="BT", fiscal_year=2022
    )
    assert metadata_store.get_companies() == ["Acme", "Beta"]
    assert metadata_store.get_years() == [2021, 2022]


def test_get_doc_ids_for_filters():
    metadata_store.upsert_document(
        doc_id="pi-f1", filename="f1.pdf", company="Acme", ticker="AC",
        fiscal_year=2021, status="completed",
    )
    metadata_store.upsert_document(
        doc_id="pi-f2", filename="f2.pdf", company="Beta", ticker="BT",
        fiscal_year=2022, status="completed",
    )
    metadata_store.upsert_document(
        doc_id="pi-f3", filename="f3.pdf", company="Acme", ticker="AC",
        fiscal_year=2022, status="processing",
    )

    # All completed
    ids = metadata_store.get_doc_ids_for_filters()
    assert set(ids) == {"pi-f1", "pi-f2"}

    # Filter by company
    ids = metadata_store.get_doc_ids_for_filters(companies=["Acme"])
    assert ids == ["pi-f1"]

    # Filter by year
    ids = metadata_store.get_doc_ids_for_filters(years=[2022])
    assert ids == ["pi-f2"]

    # Filter both
    ids = metadata_store.get_doc_ids_for_filters(companies=["Acme"], years=[2021])
    assert ids == ["pi-f1"]

    # No match
    ids = metadata_store.get_doc_ids_for_filters(companies=["Nonexistent"])
    assert ids == []
