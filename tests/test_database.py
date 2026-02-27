"""
Tests for backend.database — schema init and CRUD helpers.
"""

import os
import tempfile

import pytest

from backend.database import init_db, get_db


@pytest.fixture
def tmp_db():
    """Create a temporary database for each test."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)
    yield path
    os.unlink(path)


class TestDatabaseInit:
    def test_creates_tables(self, tmp_db):
        with get_db(tmp_db) as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
            table_names = [r["name"] for r in tables]
        assert "documents" in table_names
        assert "trees" in table_names
        assert "chunks" in table_names

    def test_idempotent(self, tmp_db):
        # Running init_db a second time should not fail
        init_db(tmp_db)
        with get_db(tmp_db) as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        assert len(tables) >= 3


class TestDocumentsCRUD:
    def test_insert_and_select(self, tmp_db):
        with get_db(tmp_db) as conn:
            conn.execute(
                """INSERT INTO documents
                   (id, company, ticker, fiscal_year, doc_type, filename, status, ingest_timestamp)
                   VALUES (?,?,?,?,?,?,?,?)""",
                ("doc1", "Infosys", "INFY", 2022, "20-F", "INFY_20F_2022.pdf", "completed", "2026-01-01"),
            )

        with get_db(tmp_db) as conn:
            row = conn.execute("SELECT * FROM documents WHERE id='doc1'").fetchone()

        assert row is not None
        assert row["company"] == "Infosys"
        assert row["ticker"] == "INFY"
        assert row["fiscal_year"] == 2022

    def test_unique_constraint(self, tmp_db):
        with get_db(tmp_db) as conn:
            conn.execute(
                """INSERT INTO documents
                   (id, company, ticker, fiscal_year, doc_type, filename, status, ingest_timestamp)
                   VALUES (?,?,?,?,?,?,?,?)""",
                ("doc1", "Infosys", "INFY", 2022, "20-F", "f1.pdf", "completed", "2026-01-01"),
            )

        with pytest.raises(Exception):
            with get_db(tmp_db) as conn:
                conn.execute(
                    """INSERT INTO documents
                       (id, company, ticker, fiscal_year, doc_type, filename, status, ingest_timestamp)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    ("doc2", "Infosys", "INFY", 2022, "20-F", "f2.pdf", "completed", "2026-01-01"),
                )

    def test_cascade_delete(self, tmp_db):
        with get_db(tmp_db) as conn:
            conn.execute(
                """INSERT INTO documents
                   (id, company, ticker, fiscal_year, doc_type, filename, status, ingest_timestamp)
                   VALUES (?,?,?,?,?,?,?,?)""",
                ("doc1", "Infosys", "INFY", 2022, "20-F", "f.pdf", "completed", "2026-01-01"),
            )
            conn.execute(
                "INSERT INTO trees (doc_id, tree_json, tree_no_text, node_map_json) VALUES (?,?,?,?)",
                ("doc1", "[]", "[]", "{}"),
            )
            conn.execute(
                """INSERT INTO chunks
                   (doc_id, node_id, chunk_index, content, token_count, embedding)
                   VALUES (?,?,?,?,?,?)""",
                ("doc1", "0000", 0, "text", 5, b"\x00" * 3072),
            )

        with get_db(tmp_db) as conn:
            conn.execute("DELETE FROM documents WHERE id='doc1'")

        with get_db(tmp_db) as conn:
            assert conn.execute("SELECT * FROM trees WHERE doc_id='doc1'").fetchone() is None
            assert conn.execute("SELECT * FROM chunks WHERE doc_id='doc1'").fetchone() is None
