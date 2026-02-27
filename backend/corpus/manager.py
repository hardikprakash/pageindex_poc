"""
Corpus manager — CRUD operations on the document store.
"""

import json
from typing import Optional

from backend.database import get_db
from backend.config import DATABASE_PATH


def list_documents(db_path: str | None = None) -> list[dict]:
    """Return summary info for all ingested documents."""
    db_path = db_path or DATABASE_PATH
    with get_db(db_path) as conn:
        rows = conn.execute(
            """SELECT id, company, ticker, fiscal_year, doc_type,
                      filename, page_count, total_tokens, node_count,
                      chunk_count, status, ingest_timestamp
               FROM documents
               ORDER BY ticker, fiscal_year"""
        ).fetchall()
    return [dict(r) for r in rows]


def get_document(doc_id: str, db_path: str | None = None) -> Optional[dict]:
    """Return full detail for a single document."""
    db_path = db_path or DATABASE_PATH
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM documents WHERE id=?", (doc_id,)
        ).fetchone()
    return dict(row) if row else None


def delete_document(doc_id: str, db_path: str | None = None) -> bool:
    """Delete a document and all associated data. Returns True if found."""
    db_path = db_path or DATABASE_PATH
    with get_db(db_path) as conn:
        cur = conn.execute("DELETE FROM documents WHERE id=?", (doc_id,))
        # cascading delete handles trees + chunks
    return cur.rowcount > 0


def get_tree(doc_id: str, db_path: str | None = None) -> Optional[dict]:
    """Return the full tree structure for a document."""
    db_path = db_path or DATABASE_PATH
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT tree_json FROM trees WHERE doc_id=?", (doc_id,)
        ).fetchone()
    if row:
        return json.loads(row["tree_json"])
    return None


def get_tree_no_text(doc_id: str, db_path: str | None = None) -> Optional[dict]:
    """Return the tree structure without text (for LLM prompts)."""
    db_path = db_path or DATABASE_PATH
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT tree_no_text FROM trees WHERE doc_id=?", (doc_id,)
        ).fetchone()
    if row:
        return json.loads(row["tree_no_text"])
    return None


def get_node_map(doc_id: str, db_path: str | None = None) -> Optional[dict]:
    """Return the flat node map {node_id → node} for a document."""
    db_path = db_path or DATABASE_PATH
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT node_map_json FROM trees WHERE doc_id=?", (doc_id,)
        ).fetchone()
    if row:
        return json.loads(row["node_map_json"])
    return None
