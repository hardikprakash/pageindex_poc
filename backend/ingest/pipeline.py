"""
Ingest pipeline — orchestrates the full flow from PDF to searchable storage.

    PDF + metadata
      → pageindex tree generation (LLM calls)
      → derive node_map & tree_no_text
      → chunk node texts
      → embed chunks via Ollama
      → write everything to SQLite
"""

import json
import logging
import os
import shutil
import uuid
from datetime import datetime, timezone

import numpy as np

from backend import config
from backend.database import get_db, init_db
from backend.ingest.chunker import chunk_text, count_tokens
from backend.ingest.embedder import embed_texts
from backend.ingest.metadata import parse_filename
from backend.models import IngestResult

logger = logging.getLogger(__name__)


# ── helpers to work with pageindex tree structures ────────────────────────────

def _structure_to_list(structure) -> list[dict]:
    """Flatten a nested tree structure into a list of nodes."""
    if isinstance(structure, dict):
        node = {k: v for k, v in structure.items() if k != "nodes"}
        nodes = [node]
        if "nodes" in structure and structure["nodes"]:
            nodes.extend(_structure_to_list(structure["nodes"]))
        return nodes
    elif isinstance(structure, list):
        nodes = []
        for item in structure:
            nodes.extend(_structure_to_list(item))
        return nodes
    return []


def _remove_fields(data, fields: list[str]):
    """Return a deep copy of *data* with specified fields stripped."""
    if isinstance(data, dict):
        return {
            k: _remove_fields(v, fields)
            for k, v in data.items()
            if k not in fields
        }
    elif isinstance(data, list):
        return [_remove_fields(item, fields) for item in data]
    return data


# ── public API ────────────────────────────────────────────────────────────────

async def ingest_pdf(
    pdf_path: str,
    company: str,
    ticker: str | None = None,
    fiscal_year: int | None = None,
    doc_type: str | None = None,
    force: bool = False,
    db_path: str | None = None,
) -> IngestResult:
    """
    Full ingest pipeline for a single PDF.

    Parameters
    ----------
    pdf_path : str
        Path to the PDF file on disk.
    company : str
        Company name (e.g. "Infosys Ltd").
    ticker, fiscal_year, doc_type : optional
        If not provided, auto-detected from the filename.
    force : bool
        If True, overwrite an existing document with the same
        (ticker, fiscal_year, doc_type) triple.
    db_path : str | None
        Override the database path (used by tests).
    """
    db_path = db_path or config.DATABASE_PATH
    init_db(db_path)

    basename = os.path.basename(pdf_path)
    doc_id = str(uuid.uuid4())

    # ── 1. Resolve metadata ──────────────────────────────────────────────────
    parsed = parse_filename(basename)
    ticker = ticker or (parsed.ticker if parsed else None)
    fiscal_year = fiscal_year or (parsed.fiscal_year if parsed else None)
    doc_type = doc_type or (parsed.doc_type if parsed else "20-F")

    if not ticker or not fiscal_year:
        return IngestResult(
            doc_id=doc_id,
            status="failed",
            message="Could not determine ticker/fiscal_year from filename or arguments.",
        )

    ticker = ticker.upper()

    # ── 2. Check for duplicates ──────────────────────────────────────────────
    with get_db(db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM documents WHERE ticker=? AND fiscal_year=? AND doc_type=?",
            (ticker, fiscal_year, doc_type),
        ).fetchone()
        if existing and not force:
            return IngestResult(
                doc_id=existing["id"],
                status="duplicate",
                message=f"Document for {ticker} {doc_type} {fiscal_year} already exists. Use force=True to overwrite.",
            )
        if existing and force:
            old_id = existing["id"]
            conn.execute("DELETE FROM chunks WHERE doc_id=?", (old_id,))
            conn.execute("DELETE FROM trees WHERE doc_id=?", (old_id,))
            conn.execute("DELETE FROM documents WHERE id=?", (old_id,))
            logger.info("Deleted existing document %s for re-ingest", old_id)

    # ── 3. Copy PDF to upload dir ────────────────────────────────────────────
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    dest_path = os.path.join(config.UPLOAD_DIR, f"{doc_id}.pdf")
    shutil.copy2(pdf_path, dest_path)

    # ── 4. Create documents row (status=processing) ─────────────────────────
    now = datetime.now(timezone.utc).isoformat()
    with get_db(db_path) as conn:
        conn.execute(
            """INSERT INTO documents
               (id, company, ticker, fiscal_year, doc_type, filename, status, ingest_timestamp)
               VALUES (?,?,?,?,?,?,?,?)""",
            (doc_id, company, ticker, fiscal_year, doc_type, basename, "processing", now),
        )

    try:
        # ── 5. Generate PageIndex tree ───────────────────────────────────────
        logger.info("Generating PageIndex tree for %s …", basename)
        tree_result = _generate_tree(dest_path)

        structure = tree_result["structure"]
        if isinstance(structure, dict):
            structure = [structure]

        # ── 6. Derive auxiliary structures ───────────────────────────────────
        tree_no_text = _remove_fields(structure, fields=["text"])
        flat_nodes = _structure_to_list(structure)
        node_map = {n["node_id"]: n for n in flat_nodes if "node_id" in n}

        page_count = _count_pages(pdf_path)
        total_tokens = sum(count_tokens(n.get("text", "")) for n in flat_nodes)

        # ── 7. Chunk node texts ──────────────────────────────────────────────
        logger.info("Chunking %d nodes …", len(flat_nodes))
        all_chunks: list[dict] = []
        for node in flat_nodes:
            node_text = node.get("text", "")
            if not node_text or not node_text.strip():
                continue
            chunks = chunk_text(node_text)
            for idx, c in enumerate(chunks):
                all_chunks.append({
                    "node_id": node.get("node_id", ""),
                    "chunk_index": idx,
                    "content": c["content"],
                    "token_count": c["token_count"],
                    "start_page": node.get("start_index"),
                    "end_page": node.get("end_index"),
                })

        # ── 8. Embed chunks ─────────────────────────────────────────────────
        logger.info("Embedding %d chunks …", len(all_chunks))
        if all_chunks:
            texts = [c["content"] for c in all_chunks]
            embeddings = await embed_texts(texts)
        else:
            embeddings = []

        # ── 9. Write to SQLite ───────────────────────────────────────────────
        logger.info("Writing to database …")
        with get_db(db_path) as conn:
            conn.execute(
                """INSERT INTO trees (doc_id, tree_json, tree_no_text, node_map_json)
                   VALUES (?,?,?,?)""",
                (
                    doc_id,
                    json.dumps(structure, ensure_ascii=False),
                    json.dumps(tree_no_text, ensure_ascii=False),
                    json.dumps(node_map, ensure_ascii=False),
                ),
            )

            for chunk_data, emb in zip(all_chunks, embeddings):
                conn.execute(
                    """INSERT INTO chunks
                       (doc_id, node_id, chunk_index, content, token_count,
                        start_page, end_page, embedding)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        doc_id,
                        chunk_data["node_id"],
                        chunk_data["chunk_index"],
                        chunk_data["content"],
                        chunk_data["token_count"],
                        chunk_data["start_page"],
                        chunk_data["end_page"],
                        emb.tobytes(),
                    ),
                )

            conn.execute(
                """UPDATE documents SET
                   page_count=?, total_tokens=?, node_count=?, chunk_count=?,
                   status='completed'
                   WHERE id=?""",
                (page_count, total_tokens, len(flat_nodes), len(all_chunks), doc_id),
            )

        logger.info("Ingest complete: %s → %s", basename, doc_id)
        return IngestResult(
            doc_id=doc_id,
            status="completed",
            chunks_created=len(all_chunks),
            node_count=len(flat_nodes),
            page_count=page_count,
            message="Ingest successful.",
        )

    except Exception as e:
        logger.exception("Ingest failed for %s", basename)
        with get_db(db_path) as conn:
            conn.execute(
                "UPDATE documents SET status='failed', error_message=? WHERE id=?",
                (str(e), doc_id),
            )
        return IngestResult(
            doc_id=doc_id,
            status="failed",
            message=f"Ingest failed: {e}",
        )


# ── private helpers ───────────────────────────────────────────────────────────

def _generate_tree(pdf_path: str) -> dict:
    """Call the local pageindex package to generate a tree structure."""
    from pageindex import page_index_main, config as pi_config

    # Ensure the pageindex LLM calls use our configured model & endpoint
    os.environ.setdefault("OPENAI_BASE_URL", config.OPENAI_BASE_URL)
    os.environ.setdefault("OPENAI_API_KEY", config.OPENAI_API_KEY)

    opt = pi_config(
        model=config.PAGEINDEX_MODEL,
        toc_check_page_num=config.TOC_CHECK_PAGES,
        max_page_num_each_node=config.MAX_PAGES_PER_NODE,
        max_token_num_each_node=config.MAX_TOKENS_PER_NODE,
        if_add_node_id="yes",
        if_add_node_summary="yes",
        if_add_doc_description="yes",
        if_add_node_text="yes",
    )

    return page_index_main(pdf_path, opt)


def _count_pages(pdf_path: str) -> int:
    """Return the number of pages in a PDF."""
    import PyPDF2
    reader = PyPDF2.PdfReader(pdf_path)
    return len(reader.pages)
