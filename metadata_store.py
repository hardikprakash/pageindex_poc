"""
Local SQLite store for document metadata (company, ticker, fiscal_year, doc_type).

PageIndex only stores doc_id / filename / page_count.  We need a local side-table
to persist the financial-filing metadata the user supplies at ingest time so the
UI can filter by company / year.
"""

from __future__ import annotations

import sqlite3
import os
from datetime import datetime, timezone
from typing import Optional

from config import METADATA_DB_PATH

_DDL = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id        TEXT PRIMARY KEY,
    filename      TEXT NOT NULL,
    company       TEXT NOT NULL DEFAULT '',
    ticker        TEXT NOT NULL DEFAULT '',
    fiscal_year   INTEGER NOT NULL DEFAULT 0,
    doc_type      TEXT NOT NULL DEFAULT '',
    page_count    INTEGER NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'processing',
    created_at    TEXT NOT NULL DEFAULT ''
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(METADATA_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(_DDL)
    return conn


# ── CRUD ─────────────────────────────────────────────────────────────────────

def upsert_document(
    doc_id: str,
    filename: str,
    company: str = "",
    ticker: str = "",
    fiscal_year: int = 0,
    doc_type: str = "",
    page_count: int = 0,
    status: str = "processing",
) -> None:
    conn = _connect()
    conn.execute(
        """
        INSERT INTO documents (doc_id, filename, company, ticker, fiscal_year, doc_type, page_count, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(doc_id) DO UPDATE SET
            filename    = excluded.filename,
            company     = excluded.company,
            ticker      = excluded.ticker,
            fiscal_year = excluded.fiscal_year,
            doc_type    = excluded.doc_type,
            page_count  = excluded.page_count,
            status      = excluded.status
        """,
        (doc_id, filename, company, ticker, fiscal_year, doc_type, page_count, status,
         datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()


def update_status(doc_id: str, status: str, page_count: int = 0) -> None:
    conn = _connect()
    if page_count:
        conn.execute(
            "UPDATE documents SET status = ?, page_count = ? WHERE doc_id = ?",
            (status, page_count, doc_id),
        )
    else:
        conn.execute(
            "UPDATE documents SET status = ? WHERE doc_id = ?",
            (status, doc_id),
        )
    conn.commit()
    conn.close()


def get_document(doc_id: str) -> Optional[dict]:
    conn = _connect()
    row = conn.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_documents() -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM documents ORDER BY company, fiscal_year"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_document(doc_id: str) -> bool:
    conn = _connect()
    cur = conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def get_companies() -> list[str]:
    conn = _connect()
    rows = conn.execute(
        "SELECT DISTINCT company FROM documents WHERE company != '' ORDER BY company"
    ).fetchall()
    conn.close()
    return [r["company"] for r in rows]


def get_years() -> list[int]:
    conn = _connect()
    rows = conn.execute(
        "SELECT DISTINCT fiscal_year FROM documents WHERE fiscal_year > 0 ORDER BY fiscal_year"
    ).fetchall()
    conn.close()
    return [r["fiscal_year"] for r in rows]


def get_doc_ids_for_filters(
    companies: list[str] | None = None,
    years: list[int] | None = None,
) -> list[str]:
    """Return PageIndex doc_ids matching optional company / year filters."""
    conn = _connect()
    query = "SELECT doc_id FROM documents WHERE status = 'completed'"
    params: list = []

    if companies:
        placeholders = ",".join("?" for _ in companies)
        query += f" AND company IN ({placeholders})"
        params.extend(companies)

    if years:
        placeholders = ",".join("?" for _ in years)
        query += f" AND fiscal_year IN ({placeholders})"
        params.extend(years)

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [r["doc_id"] for r in rows]
