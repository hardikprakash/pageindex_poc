# API Contract — FastAPI Endpoints

## 1. Overview

The FastAPI backend exposes three endpoint groups that match what the existing
Streamlit frontend expects. All JSON responses are designed to be consumed
directly by `frontend/app.py` without modification.

**Base URL:** `http://localhost:8000`

---

## 2. Endpoints

### 2.1 `GET /corpus` — List Ingested Documents

Returns summary information for all ingested documents.

**Response (200):**
```json
{
    "documents": [
        {
            "id": "abc-123",
            "company": "Apple Inc.",
            "ticker": "AAPL",
            "fiscal_year": 2023,
            "doc_type": "20-F",
            "chunk_count": 142,
            "fact_count": 0,
            "node_count": 35,
            "page_count": 210,
            "status": "completed",
            "ingest_timestamp": "2026-02-27T10:30:00"
        },
        ...
    ]
}
```

**Notes:**
- `fact_count` is kept at 0 for compatibility with the Graph RAG frontend
  (we don't extract structured facts in this pipeline).
- The frontend uses `company`, `fiscal_year`, `chunk_count`, and
  `ingest_timestamp` for display.

---

### 2.2 `POST /ingest` — Upload and Process a PDF

Accepts a PDF file upload with metadata. Kicks off background tree generation.

**Request:** `multipart/form-data`

| Field | Type | Required | Description |
|---|---|---|---|
| `file` | File (PDF) | Yes | The PDF filing |
| `company` | string | Yes | Company name |
| `ticker` | string | Yes | Ticker / short ID |
| `fiscal_year` | string | Yes | Fiscal year (as string, parsed to int) |
| `doc_type_hint` | string | No | "20-F", "10-K", etc. Defaults to "20-F" |

**Response (200) — Ingest Accepted:**
```json
{
    "doc_id": "abc-123",
    "status": "processing",
    "message": "Document accepted for processing",
    "chunks_created": 0,
    "facts_created": 0,
    "entities_created": 0
}
```

**Response (200) — Ingest Complete (if synchronous mode):**
```json
{
    "doc_id": "abc-123",
    "status": "completed",
    "chunks_created": 142,
    "facts_created": 0,
    "entities_created": 0,
    "node_count": 35,
    "page_count": 210
}
```

**Response (409) — Duplicate Filing:**
```json
{
    "detail": "Document for AAPL 2023 20-F already exists. Use ?force=true to overwrite."
}
```

**Notes:**
- The frontend expects `chunks_created`, `facts_created`, `entities_created`
  in the success response. We return 0 for `facts` and `entities` for compat.
- For the PoC, ingest may run synchronously (blocking the request) since
  the frontend shows a progress spinner per file. If desired, we can add
  a background task with polling.

---

### 2.3 `POST /query` — Ask a Question

Runs the full hybrid retrieval + answer generation pipeline.

**Request:**
```json
{
    "query": "How did Apple's revenue change from 2021 to 2023?",
    "companies": ["Apple Inc."],
    "years": [2021, 2022, 2023]
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `query` | string | Yes | Natural language question |
| `companies` | list[string] | No | Filter by company name |
| `years` | list[int] | No | Filter by fiscal year |

**Response (200):**
```json
{
    "answer": "Apple's revenue grew from $365.8B in FY2021 to $394.3B in FY2023 [Apple, 2021, p45] [Apple, 2023, p52]...",
    "retrieval_confidence": {
        "label": "HIGH",
        "answered_by_facts": 2,
        "answered_by_chunks": 5,
        "unanswered": 0
    },
    "resolved_citations": [
        {
            "key": "AAPL-2021-revenue",
            "company": "Apple Inc.",
            "ticker": "AAPL",
            "fiscal_year": 2021,
            "doc_type": "20-F",
            "section_path": "Financial Statements > Revenue",
            "page": 45,
            "node_id": "0012",
            "chunk_type": "tree_node",
            "confidence": "high",
            "content_preview": "Total net revenue for the fiscal year ended..."
        },
        ...
    ],
    "unanswerable_sub_questions": [],
    "conflicts_detected": []
}
```

**Response (422):**
```json
{
    "detail": "Query must not be empty"
}
```

**Notes:**
- `resolved_citations` follows the schema the frontend renders in
  `render_citations()`: grouped by `(company, fiscal_year)`, with
  `confidence`, `key`, `section_path`, `page`, `chunk_type`, and
  `content_preview`.
- `answered_by_facts` maps to "sub-questions fully answered" in our pipeline
  (re-purposed from the Graph RAG terminology).
- `answered_by_chunks` = number of distinct tree nodes used.

---

### 2.4 `GET /health` — Health Check (new)

```json
{
    "status": "ok",
    "ollama": "connected",
    "llm": "connected",
    "documents": 8
}
```

---

## 3. Models (Pydantic)

```python
from pydantic import BaseModel
from typing import Optional

class IngestRequest(BaseModel):
    company: str
    ticker: str
    fiscal_year: int
    doc_type_hint: str = "20-F"

class QueryRequest(BaseModel):
    query: str
    companies: list[str] = []
    years: list[int] = []

class Citation(BaseModel):
    key: str
    company: str
    ticker: str
    fiscal_year: int
    doc_type: str
    section_path: str
    page: int
    node_id: str
    chunk_type: str = "tree_node"
    confidence: str = "medium"
    content_preview: str = ""

class RetrievalConfidence(BaseModel):
    label: str        # HIGH, MEDIUM, LOW
    answered_by_facts: int
    answered_by_chunks: int
    unanswered: int

class QueryResponse(BaseModel):
    answer: str
    retrieval_confidence: RetrievalConfidence
    resolved_citations: list[Citation]
    unanswerable_sub_questions: list[str] = []
    conflicts_detected: list[str] = []

class CorpusDocument(BaseModel):
    id: str
    company: str
    ticker: str
    fiscal_year: int
    doc_type: str
    chunk_count: int = 0
    fact_count: int = 0
    node_count: int = 0
    page_count: int = 0
    status: str = "completed"
    ingest_timestamp: Optional[str] = None

class CorpusResponse(BaseModel):
    documents: list[CorpusDocument]
```

---

## 4. CORS & Configuration

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Environment variables:
```bash
OPENAI_API_KEY=<openrouter key>
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OLLAMA_URL=http://localhost:11435
DATABASE_PATH=data/pageindex.db
```
