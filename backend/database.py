"""
SQLite database initialisation and helpers.
"""

import os
import sqlite3
from contextlib import contextmanager

from backend.config import DATABASE_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id              TEXT PRIMARY KEY,
    company         TEXT NOT NULL,
    ticker          TEXT NOT NULL,
    fiscal_year     INTEGER NOT NULL,
    doc_type        TEXT NOT NULL DEFAULT '20-F',
    filename        TEXT NOT NULL,
    page_count      INTEGER,
    total_tokens    INTEGER,
    node_count      INTEGER DEFAULT 0,
    chunk_count     INTEGER DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'processing',
    error_message   TEXT,
    ingest_timestamp TEXT NOT NULL,
    UNIQUE(ticker, fiscal_year, doc_type)
);

CREATE TABLE IF NOT EXISTS trees (
    doc_id          TEXT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
    tree_json       TEXT NOT NULL,
    tree_no_text    TEXT NOT NULL,
    node_map_json   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id          TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    node_id         TEXT NOT NULL,
    chunk_index     INTEGER NOT NULL,
    content         TEXT NOT NULL,
    token_count     INTEGER NOT NULL,
    start_page      INTEGER,
    end_page        INTEGER,
    embedding       BLOB NOT NULL,
    UNIQUE(doc_id, node_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_node ON chunks(doc_id, node_id);
"""


def _ensure_dir():
    db_dir = os.path.dirname(DATABASE_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)


def init_db(db_path: str | None = None):
    """Create tables if they don't exist yet."""
    path = db_path or DATABASE_PATH
    _ensure_dir()
    conn = sqlite3.connect(path)
    conn.executescript(_SCHEMA)
    conn.close()


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or DATABASE_PATH
    _ensure_dir()
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_db(db_path: str | None = None):
    """Context manager that yields a connection and auto-commits/rollbacks."""
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
