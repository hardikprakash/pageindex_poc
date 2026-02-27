"""
Tests for backend.corpus.manager — corpus CRUD operations.
"""

import json
import os
import tempfile

import pytest

from backend.database import init_db, get_db
from backend.corpus.manager import (
    list_documents,
    get_document,
    delete_document,
    get_tree,
    get_tree_no_text,
    get_node_map,
)


@pytest.fixture
def tmp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)
    yield path
    os.unlink(path)


@pytest.fixture
def seeded_db(tmp_db):
    """DB with one document + tree + chunks."""
    tree = [{"title": "Root", "node_id": "0000", "text": "root text", "summary": "root summary",
             "start_index": 1, "end_index": 5, "nodes": [
                 {"title": "Child", "node_id": "0001", "text": "child text", "summary": "child summary",
                  "start_index": 1, "end_index": 3}
             ]}]
    tree_no_text = [{"title": "Root", "node_id": "0000", "summary": "root summary",
                     "nodes": [{"title": "Child", "node_id": "0001", "summary": "child summary"}]}]
    node_map = {
        "0000": {"title": "Root", "node_id": "0000", "text": "root text"},
        "0001": {"title": "Child", "node_id": "0001", "text": "child text"},
    }

    with get_db(tmp_db) as conn:
        conn.execute(
            """INSERT INTO documents
               (id, company, ticker, fiscal_year, doc_type, filename,
                page_count, node_count, chunk_count, status, ingest_timestamp)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            ("doc1", "Infosys", "INFY", 2022, "20-F", "INFY_20F_2022.pdf",
             100, 2, 3, "completed", "2026-01-01"),
        )
        conn.execute(
            "INSERT INTO trees (doc_id, tree_json, tree_no_text, node_map_json) VALUES (?,?,?,?)",
            ("doc1", json.dumps(tree), json.dumps(tree_no_text), json.dumps(node_map)),
        )
        for i in range(3):
            conn.execute(
                """INSERT INTO chunks
                   (doc_id, node_id, chunk_index, content, token_count, embedding)
                   VALUES (?,?,?,?,?,?)""",
                ("doc1", "0000", i, f"chunk {i}", 10, b"\x00" * 3072),
            )

    return tmp_db


class TestListDocuments:
    def test_empty(self, tmp_db):
        assert list_documents(tmp_db) == []

    def test_returns_seeded(self, seeded_db):
        docs = list_documents(seeded_db)
        assert len(docs) == 1
        assert docs[0]["ticker"] == "INFY"
        assert docs[0]["fiscal_year"] == 2022
        assert docs[0]["chunk_count"] == 3


class TestGetDocument:
    def test_found(self, seeded_db):
        doc = get_document("doc1", seeded_db)
        assert doc is not None
        assert doc["company"] == "Infosys"

    def test_not_found(self, seeded_db):
        assert get_document("nonexistent", seeded_db) is None


class TestDeleteDocument:
    def test_delete_existing(self, seeded_db):
        assert delete_document("doc1", seeded_db) is True
        assert get_document("doc1", seeded_db) is None
        # Cascaded
        assert get_tree("doc1", seeded_db) is None

    def test_delete_nonexistent(self, seeded_db):
        assert delete_document("nonexistent", seeded_db) is False


class TestGetTree:
    def test_returns_tree(self, seeded_db):
        tree = get_tree("doc1", seeded_db)
        assert tree is not None
        assert tree[0]["title"] == "Root"
        assert "text" in tree[0]

    def test_not_found(self, seeded_db):
        assert get_tree("nonexistent", seeded_db) is None


class TestGetTreeNoText:
    def test_returns_tree_without_text(self, seeded_db):
        tree = get_tree_no_text("doc1", seeded_db)
        assert tree is not None
        assert "text" not in tree[0]
        assert tree[0]["title"] == "Root"

    def test_not_found(self, seeded_db):
        assert get_tree_no_text("nonexistent", seeded_db) is None


class TestGetNodeMap:
    def test_returns_map(self, seeded_db):
        nmap = get_node_map("doc1", seeded_db)
        assert nmap is not None
        assert "0000" in nmap
        assert nmap["0000"]["title"] == "Root"
        assert "0001" in nmap

    def test_not_found(self, seeded_db):
        assert get_node_map("nonexistent", seeded_db) is None
