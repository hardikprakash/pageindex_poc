"""
FastAPI application — POST /query, GET /corpus, POST /ingest, DELETE /corpus/{doc_id}.

All heavy lifting is done by PageIndex Cloud API; this backend is a thin wrapper
that adds local metadata management and filters.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pageindex import PageIndexClient

from api.models import (
    QueryRequest,
    QueryResponse,
    IngestResponse,
    CorpusResponse,
    DocumentInfo,
)
from config import PAGEINDEX_API_KEY
import metadata_store

logger = logging.getLogger(__name__)

# ── Globals ──────────────────────────────────────────────────────────────────
_pi: PageIndexClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pi
    if not PAGEINDEX_API_KEY:
        raise RuntimeError("PAGEINDEX_API_KEY is not set. Get one at https://dash.pageindex.ai/api-keys")
    _pi = PageIndexClient(api_key=PAGEINDEX_API_KEY)
    logger.info("PageIndex client initialised.")
    yield
    _pi = None


app = FastAPI(
    title="Financial Filings PageIndex Agent",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── POST /query ──────────────────────────────────────────────────────────────

@app.post("/query", response_model=QueryResponse)
async def query_endpoint(request: QueryRequest):
    """
    Query financial documents via PageIndex Chat API.
    Filters by company / year from local metadata, then passes matching doc_ids
    to PageIndex for agentic retrieval.
    """
    # Resolve doc_ids from filters
    doc_ids = metadata_store.get_doc_ids_for_filters(
        companies=request.companies or None,
        years=request.years or None,
    )
    if not doc_ids:
        raise HTTPException(
            status_code=422,
            detail="No documents match the selected filters. Ingest some documents first.",
        )

    # Call PageIndex Chat API (non-streaming for the REST endpoint)
    try:
        if len(doc_ids) == 1:
            doc_id_param = doc_ids[0]
        else:
            doc_id_param = doc_ids

        response = _pi.chat_completions(
            messages=[{"role": "user", "content": request.query}],
            doc_id=doc_id_param,
            stream=False,
            enable_citations=True,
        )

        answer_text = response["choices"][0]["message"]["content"]
        usage = response.get("usage", {})

        # Parse inline citations like <doc=file.pdf;page=1>
        citations = _extract_citations(answer_text)

        return QueryResponse(
            answer=answer_text,
            query=request.query,
            doc_ids_used=doc_ids,
            citations=citations,
            usage=usage,
        )
    except Exception as e:
        logger.error(f"PageIndex query failed: {e}")
        raise HTTPException(status_code=500, detail=f"PageIndex query failed: {e}")


@app.post("/query/stream")
async def query_stream_endpoint(request: QueryRequest):
    """
    Streaming version of /query — returns Server-Sent Events.
    """
    doc_ids = metadata_store.get_doc_ids_for_filters(
        companies=request.companies or None,
        years=request.years or None,
    )
    if not doc_ids:
        raise HTTPException(
            status_code=422,
            detail="No documents match the selected filters.",
        )

    if len(doc_ids) == 1:
        doc_id_param = doc_ids[0]
    else:
        doc_id_param = doc_ids

    def generate():
        try:
            for chunk in _pi.chat_completions(
                messages=[{"role": "user", "content": request.query}],
                doc_id=doc_id_param,
                stream=True,
                enable_citations=True,
            ):
                yield f"data: {chunk}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: [ERROR] {e}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ── GET /corpus ──────────────────────────────────────────────────────────────

@app.get("/corpus", response_model=CorpusResponse)
async def get_corpus():
    """Returns all ingested documents with their metadata."""
    docs = metadata_store.list_documents()
    # Refresh status for any still-processing docs
    for doc in docs:
        if doc["status"] not in ("completed", "failed"):
            try:
                info = _pi.get_document(doc["doc_id"])
                new_status = info.get("status", doc["status"])
                page_count = info.get("pageNum", 0)
                if new_status != doc["status"]:
                    metadata_store.update_status(doc["doc_id"], new_status, page_count)
                    doc["status"] = new_status
                    doc["page_count"] = page_count
            except Exception:
                pass

    return CorpusResponse(
        documents=[DocumentInfo(**d) for d in docs]
    )


# ── POST /ingest ─────────────────────────────────────────────────────────────

@app.post("/ingest", response_model=IngestResponse)
async def ingest_document(
    file: UploadFile,
    company: str = Form(...),
    ticker: str = Form(...),
    fiscal_year: int = Form(...),
    doc_type_hint: str = Form(""),
):
    """
    Accept a PDF, upload to PageIndex for tree generation, and store metadata locally.
    """
    # Save uploaded file to temp location
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = _pi.submit_document(tmp_path)
        doc_id = result["doc_id"]

        # Store meta locally
        metadata_store.upsert_document(
            doc_id=doc_id,
            filename=file.filename or os.path.basename(tmp_path),
            company=company,
            ticker=ticker,
            fiscal_year=fiscal_year,
            doc_type=doc_type_hint,
            status="processing",
        )

        # Poll briefly to see if it completes fast
        import asyncio
        for _ in range(3):
            await asyncio.sleep(2)
            info = _pi.get_document(doc_id)
            status = info.get("status", "processing")
            page_count = info.get("pageNum", 0)
            if status == "completed":
                metadata_store.update_status(doc_id, "completed", page_count)
                return IngestResponse(
                    doc_id=doc_id,
                    filename=file.filename or "",
                    status="completed",
                    page_count=page_count,
                )

        # Still processing — return early, status will be refreshed on /corpus
        return IngestResponse(
            doc_id=doc_id,
            filename=file.filename or "",
            status="processing",
            page_count=0,
        )
    finally:
        os.unlink(tmp_path)


# ── DELETE /corpus/{doc_id} ──────────────────────────────────────────────────

@app.delete("/corpus/{doc_id}")
async def delete_corpus_document(doc_id: str):
    """Delete a document from both PageIndex and local metadata."""
    try:
        _pi.delete_document(doc_id)
    except Exception as e:
        logger.warning(f"PageIndex delete failed for {doc_id}: {e}")

    deleted = metadata_store.delete_document(doc_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found.")
    return {"deleted": doc_id}


# ── GET /health ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "pageindex_configured": bool(PAGEINDEX_API_KEY)}


# ── Helpers ──────────────────────────────────────────────────────────────────

_CITATION_RE = re.compile(r"<doc=([^;>]+);page=(\d+)>")


def _extract_citations(text: str) -> list[dict]:
    """Extract inline citations like <doc=file.pdf;page=1> from response text."""
    citations = []
    seen = set()
    for match in _CITATION_RE.finditer(text):
        doc_name = match.group(1)
        page = int(match.group(2))
        key = (doc_name, page)
        if key not in seen:
            seen.add(key)
            citations.append({"document": doc_name, "page": page})
    return citations
