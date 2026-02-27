# Frontend Adaptation — Streamlit Changes

## 1. Goal

Minimally adapt the existing `frontend/app.py` (originally built for a
Graph RAG backend) to work with our PageIndex-based FastAPI backend.

The API contract (doc 06) was **designed to match** the frontend's existing
expectations, so **most of the frontend can remain unchanged**.

---

## 2. Changes Required

### 2.1 No Changes Needed (compatible as-is)

| Component | Reason |
|---|---|
| `render_query_page()` | Sends `POST /query` with `{query, companies, years}` — same contract |
| `render_answer()` | Reads `answer`, `retrieval_confidence`, `resolved_citations` — same schema |
| `render_citations()` | Groups by `(company, fiscal_year)`, reads `confidence`, `key`, `section_path`, `page`, `chunk_type`, `content_preview` — all provided |
| `render_corpus_tab()` | Calls `GET /corpus`, reads `documents` list with `company`, `ticker`, `fiscal_year`, `doc_type`, `chunk_count` — all provided |
| `render_ingest_tab()` | Sends `POST /ingest` with multipart form — same fields |
| Sidebar filters | Reads `company` and `fiscal_year` from corpus — works |
| Query history | Client-side session state — no backend dependency |

### 2.2 Minor Recommended Changes

These are **optional cosmetic tweaks** to better reflect the PageIndex-based
backend instead of the Graph RAG origin:

| Change | File | Details |
|---|---|---|
| Page title | `app.py` L18 | "Financial Filings Agent" → "Financial Filings Agent (PageIndex)" |
| About text | `app.py` L79-83 | Update description from "Graph RAG" to "PageIndex tree search" |
| Ingest success message | `app.py` L299 | Show `node_count` alongside `chunks_created`; `facts_created` and `entities_created` will be 0 |
| Confidence tooltip | `app.py` L148 | Update "facts" label to "answered sub-questions" for clarity |

### 2.3 Potential Enhancements (post-MVP)

| Enhancement | Description |
|---|---|
| Tree visualization | Show the PageIndex tree for a selected document (collapsible tree widget) |
| Node highlight | When viewing citations, show which tree nodes were selected |
| Ingest status polling | Poll `GET /corpus/{doc_id}` for real-time ingest progress |
| Reasoning trace | Show the LLM's "thinking" from tree search in a debug expander |

---

## 3. Environment Variable

The frontend already reads `BACKEND_URL` from environment:

```python
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
```

No change needed.

---

## 4. Running the Frontend

```bash
# Terminal 1: Backend
uvicorn backend.main:app --host 0.0.0.0 --port 8000

# Terminal 2: Frontend
streamlit run frontend/app.py
```
