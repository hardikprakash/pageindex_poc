# PageIndex PoC — Financial Filing Q&A System

A re-implementation of [PageIndex](https://github.com/nicholasgasior/pageindex) for querying and analyzing multi-year, multi-company financial filings (Form 20-F, 10-K, etc.) using semantic tree structures, chunk embeddings, and hybrid retrieval.

## Overview

Instead of traditional vector-only RAG, this system uses the **PageIndex** library to build hierarchical semantic trees from long PDF documents. Each document is parsed into a tree of titled sections with page ranges. The node texts are then chunked, embedded (via Ollama), and stored alongside the tree in SQLite for hybrid retrieval at query time.

### What's Working Today

| Layer | Status | Details |
|-------|--------|---------|
| **Ingestion pipeline** | ✅ Complete | PDF → PageIndex tree → chunk → embed → SQLite |
| **CLI tooling** | ✅ Complete | Single-doc & batch ingest with pre-flight checks |
| **Corpus management** | ✅ Complete | List, get, delete documents; cascade deletes |
| **Embeddings (Ollama)** | ✅ Complete | `nomic-embed-text-v2-moe` (768-d), batched, retries |
| **Unit tests** | ✅ Complete | 56 tests, 100 % passing |
| **Streamlit frontend** | ✅ Scaffold | Query page + corpus page; needs FastAPI backend |
| **Retrieval pipeline** | 🚧 Planned | Value search + LLM tree search + hybrid merge |
| **FastAPI backend** | 🚧 Planned | `/corpus`, `/ingest`, `/query`, `/health` |

## Quick Start

### Prerequisites

- Python 3.11+ (tested on 3.12)
- Docker & Docker Compose (for Ollama embeddings)
- An [OpenRouter](https://openrouter.ai/) API key (or any OpenAI-compatible endpoint)

### 1. Clone & create virtual environment

```bash
git clone <repo-url> && cd pageindex_poc
python -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
pip install pytest pytest-asyncio httpx numpy  # dev / test extras
```

### 3. Configure environment

Create a `.env` file in the project root:

```dotenv
OPENAI_API_KEY=sk-or-v1-xxxxx
OPENAI_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=openai/gpt-oss-120b
```

### 4. Start Ollama (embedding service)

```bash
docker compose up -d
```

This starts `ollama-pageindex` on port **11435** with GPU support. Pull the embedding model on first run:

```bash
docker exec ollama-pageindex ollama pull nomic-embed-text-v2-moe
```

### 5. Ingest a document

```bash
python -m scripts.ingest --pdf data/INFY_20F_2022.pdf --company "Infosys"
```

The script runs **pre-flight checks** (API key present, Ollama reachable, embedding model loaded) before starting the expensive LLM tree generation.

## Ingestion Pipeline

### How It Works

```
PDF file
  │
  ├─ 1. Metadata auto-detected from filename (TICKER_DOCTYPE_YEAR.pdf)
  ├─ 2. Duplicate check against (ticker, fiscal_year, doc_type)
  ├─ 3. PageIndex tree generation (LLM calls via OpenRouter)
  │     └─ Produces hierarchical sections with summaries + page ranges + text
  ├─ 4. Derive auxiliary structures (tree_no_text, node_map)
  ├─ 5. Chunk node texts (512 tokens, 64 overlap, min 32)
  ├─ 6. Embed chunks via Ollama (768-d, batches of 32)
  └─ 7. Write to SQLite (documents + trees + chunks tables)
```

### Filename Convention

PDFs must follow: **`TICKER_DOCTYPE_YEAR.pdf`**

| Example | Ticker | Doc Type | Year |
|---------|--------|----------|------|
| `INFY_20F_2022.pdf` | INFY | 20-F | 2022 |
| `TCS_10K_2023.pdf` | TCS | 10-K | 2023 |
| `AAPL_20F_2021.pdf` | AAPL | 20-F | 2021 |

You can also supply metadata explicitly with `--ticker`, `--year`, `--doc-type` flags.

### CLI Reference

**Single document:**
```bash
python -m scripts.ingest --pdf data/INFY_20F_2022.pdf --company "Infosys"
```

**Batch ingestion** (all PDFs in a directory):
```bash
python -m scripts.ingest --dir data/pdfs/ --company-map data/company_map.json
```

The company map maps tickers to company names:
```json
{
  "INFY": "Infosys Ltd",
  "TCS": "Tata Consultancy Services"
}
```

**Force re-ingest** (overwrite existing document):
```bash
python -m scripts.ingest --pdf data/INFY_20F_2022.pdf --company "Infosys" --force
```

**Explicit metadata override:**
```bash
python -m scripts.ingest --pdf data/report.pdf \
    --company "Infosys" --ticker INFY --year 2022 --doc-type 20-F
```

### Pre-flight Checks

The ingest script verifies before starting:

1. `OPENAI_API_KEY` is set
2. Ollama is reachable and the configured embedding model is loaded

If either check fails, the script exits with a clear error message before any LLM calls are made.

### Example Output

```
00:00:17 │ INFO  │ ingest │ ✓ OpenRouter API key found
00:00:17 │ INFO  │ ingest │ ✓ Ollama reachable at http://localhost:11435 (model: nomic-embed-text-v2-moe)
00:00:17 │ INFO  │ ingest │ ▶ Ingesting INFY_20F_2022.pdf
...
01:02:12 │ INFO  │ ingest │ ✓ INFY_20F_2022.pdf → 76b1dee3...  |  70 nodes, 336 chunks, 57 pages  [1077.2s]
01:02:12 │ INFO  │ ingest │ Done: 1 succeeded, 0 failed, 1 total
```

> **Note:** Tree generation is the slowest step (~5–15 min per document) since it makes many LLM calls to build and verify the hierarchical structure.

## Frontend (Streamlit)

The frontend is a Streamlit app with two pages. It communicates with the FastAPI backend via HTTP.

### Running the Frontend

```bash
streamlit run frontend/app.py
```

By default it connects to `http://localhost:8000`. Override with:
```bash
BACKEND_URL=http://your-server:8000 streamlit run frontend/app.py
```

### Pages

**Query Page** — Ask questions about ingested financial filings:
- Free-text query input
- Filter by company and fiscal year
- Confidence threshold slider (LOW / MEDIUM / HIGH)
- Displays answer with source citations, conflict detection, and debug panel
- Query history in the sidebar

**Corpus Page** — Manage ingested documents:
- *Ingested Documents* tab: summary metrics (doc count, companies, years, chunks) + full document table
- *Ingest New* tab: upload PDFs via the browser, specify company/ticker/year, and trigger ingestion

> **Note:** The frontend requires the FastAPI backend to be running. The backend is planned but not yet implemented — the frontend scaffold is ready for integration once the backend endpoints exist.

## Testing

```bash
# Run all 56 tests
python -m pytest tests/ -v

# Run a specific module
python -m pytest tests/test_pipeline.py -v

# With coverage
python -m pytest tests/ --cov=backend
```

### Test Suite Breakdown

| Module | Tests | What It Covers |
|--------|-------|----------------|
| `test_metadata.py` | 12 | Filename parsing, case normalization, edge cases |
| `test_chunker.py` | 8 | Token counting, chunk splitting, overlap, min-size filter |
| `test_database.py` | 5 | Schema creation, CRUD, unique constraints, cascading deletes |
| `test_corpus.py` | 12 | Document list/get/delete, tree retrieval |
| `test_embedder.py` | 3 | Embedding generation, batching logic |
| `test_pipeline.py` | 16 | Full ingest flow (mocked externals), duplicates, force re-ingest |

All external services (PageIndex LLM calls, Ollama) are mocked in tests — no API keys or Docker needed to run the suite.

## Project Structure

```
pageindex_poc/
├── backend/
│   ├── config.py              # Env var configuration
│   ├── database.py            # SQLite schema + connection helpers
│   ├── models.py              # Pydantic schemas (DocumentRecord, IngestResult, ParsedMetadata)
│   ├── corpus/
│   │   └── manager.py         # Document CRUD operations
│   ├── ingest/
│   │   ├── metadata.py        # TICKER_DOCTYPE_YEAR filename parser
│   │   ├── chunker.py         # Token-aware text chunking (tiktoken)
│   │   ├── embedder.py        # Ollama HTTP embedding client
│   │   └── pipeline.py        # Full ingest orchestration
│   ├── llm/
│   │   └── client.py          # Async OpenRouter LLM wrapper
│   └── retrieval/             # (planned) Hybrid search modules
├── frontend/
│   └── app.py                 # Streamlit UI (Query + Corpus pages)
├── pageindex/                 # Local PageIndex library (tree generation)
├── scripts/
│   └── ingest.py              # Ingestion CLI with pre-flight checks
├── tests/                     # 56 unit tests
├── docs/
│   ├── context/               # PageIndex reference materials
│   └── design/                # 8 design documents (architecture, API, etc.)
├── data/
│   ├── uploads/               # Copies of ingested PDFs
│   └── pageindex.db           # SQLite database
├── docker-compose.yaml        # Ollama GPU service
├── requirements.txt           # Python dependencies
├── run_pageindex.py           # Standalone PageIndex runner (for experimentation)
├── .env                       # API keys and config (not committed)
└── .gitignore
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | *(required)* | OpenRouter API key |
| `OPENAI_BASE_URL` | `https://openrouter.ai/api/v1` | LLM endpoint |
| `LLM_MODEL` | `openai/gpt-5.2` | LLM model for tree generation and queries |
| `OLLAMA_URL` | `http://localhost:11435` | Ollama embedding service |
| `EMBEDDING_MODEL` | `nomic-embed-text-v2-moe` | Ollama embedding model |
| `EMBEDDING_DIM` | `768` | Embedding vector dimension |
| `DATABASE_PATH` | `data/pageindex.db` | SQLite database location |
| `UPLOAD_DIR` | `data/uploads` | Where ingested PDFs are copied |
| `CHUNK_MAX_TOKENS` | `512` | Max tokens per chunk |
| `CHUNK_OVERLAP_TOKENS` | `64` | Token overlap between chunks |
| `CHUNK_MIN_TOKENS` | `32` | Minimum chunk size (smaller chunks dropped) |
| `EMBED_BATCH_SIZE` | `32` | Texts per Ollama embedding request |
| `PAGEINDEX_MODEL` | *(same as LLM_MODEL)* | Model for PageIndex tree generation |
| `TOC_CHECK_PAGES` | `20` | Pages to scan for table of contents |
| `MAX_PAGES_PER_NODE` | `10` | Max pages per tree node before subdivision |
| `MAX_TOKENS_PER_NODE` | `20000` | Max tokens per tree node |
| `BACKEND_URL` | `http://localhost:8000` | Backend URL (used by Streamlit frontend) |

### Database Schema

Three tables with cascading deletes:

- **documents** — Document metadata: `id`, `company`, `ticker`, `fiscal_year`, `doc_type`, `filename`, `page_count`, `total_tokens`, `node_count`, `chunk_count`, `status`, `ingest_timestamp`. Unique on `(ticker, fiscal_year, doc_type)`.
- **trees** — Full PageIndex tree JSON, stripped tree (no text), and flat node map. One row per document.
- **chunks** — Text chunks with token count, page range, and 768-d embedding stored as BLOB. Indexed on `(doc_id)` and `(doc_id, node_id)`.

## Common Operations

### Resetting Data & Ingesting New Documents

**Full reset:**
```bash
rm -f data/pageindex.db data/pageindex.db-wal data/pageindex.db-shm
rm -rf data/uploads/

# Re-ingest (database auto-created on first run)
python -m scripts.ingest --dir data/pdfs/ --company-map data/company_map.json
```

**Delete a single document** (tree + chunks cascade-deleted):
```python
from backend.corpus.manager import list_documents, delete_document

for doc in list_documents():
    print(doc["id"], doc["ticker"], doc["fiscal_year"], doc["doc_type"])

delete_document("the-doc-id-here")
```

**Replace a single document:**
```bash
python -m scripts.ingest --pdf data/INFY_20F_2022.pdf --company "Infosys" --force
```

### Re-embedding with a Different Model

Since embeddings are stored per-chunk, switching models requires a full re-ingest.

**1. Update `.env`:**
```dotenv
EMBEDDING_MODEL=mxbai-embed-large
EMBEDDING_DIM=1024
```

**2. Pull the new model into Ollama:**
```bash
docker exec ollama-pageindex ollama pull mxbai-embed-large
curl http://localhost:11435/api/tags  # verify
```

**3. Wipe and re-ingest:**
```bash
rm -f data/pageindex.db data/pageindex.db-wal data/pageindex.db-shm
python -m scripts.ingest --dir data/pdfs/ --company-map data/company_map.json
```

**Common Ollama embedding models:**

| Model | Dimensions | Notes |
|-------|-----------|-------|
| `nomic-embed-text-v2-moe` | 768 | Default — good balance of quality & speed |
| `mxbai-embed-large` | 1024 | Higher quality, slightly slower |
| `all-minilm` | 384 | Fastest, lower quality |
| `snowflake-arctic-embed` | 1024 | Strong multilingual support |

## Troubleshooting

### Ollama Not Reachable
```bash
# Check status
curl http://localhost:11435/api/tags

# Restart
docker compose restart ollama-pageindex

# Check logs
docker compose logs ollama-pageindex
```

### Pre-flight Check Fails
The ingest script will print exactly what's wrong:
```
✗ OPENAI_API_KEY is not set. Add it to your .env file (format: sk-or-v1-...).
✗ Ollama is not reachable at http://localhost:11435 or model 'nomic-embed-text-v2-moe' is not loaded. Run: docker compose up -d
```

### Ingestion Fails Mid-Way
If the LLM accuracy check for a large node drops below 60 %, the node is kept as a flat leaf instead of crashing the ingest. A warning is logged:
```
Could not subdivide large node "9. Risks related to the ADSs" — keeping as leaf node.
```

### Database Reset
```bash
rm -f data/pageindex.db data/pageindex.db-wal data/pageindex.db-shm
```
The database is auto-created on the next ingest run.

### OpenRouter API Errors
- Verify API key in `.env` (format: `sk-or-v1-...`)
- Check account credits at [openrouter.ai/credits](https://openrouter.ai/credits)
- Ensure base URL is `https://openrouter.ai/api/v1`

## Development Roadmap

### ✅ Complete
- [x] Design & architecture documentation (8 design docs)
- [x] Ingestion pipeline (PDF → PageIndex tree → chunk → embed → SQLite)
- [x] Metadata parser (TICKER_DOCTYPE_YEAR filename convention)
- [x] Token-aware chunker with overlap (tiktoken cl100k_base)
- [x] Ollama embedding client with batching and retries
- [x] SQLite database with WAL mode + cascading deletes
- [x] CLI ingestion script with pre-flight service checks
- [x] Corpus manager (CRUD operations)
- [x] Async LLM client (OpenRouter via OpenAI SDK)
- [x] Streamlit frontend scaffold (Query + Corpus pages)
- [x] 56 unit tests (100 % passing, all externals mocked)
- [x] Real-document ingestion tested (INFY 20-F 2022: 70 nodes, 336 chunks, 57 pages)

### 🚧 Planned
- [ ] Retrieval pipeline — value-based search (embed query → cosine similarity → node scoring)
- [ ] Retrieval pipeline — LLM tree search (prompt LLM with tree structure → node selection)
- [ ] Hybrid merge & deduplication of retrieval results
- [ ] Answer generation with page/node citations
- [ ] FastAPI backend (`/corpus`, `/ingest`, `/query`, `/health`)
- [ ] Frontend ↔ backend integration (currently scaffold only)
- [ ] End-to-end testing across multiple companies and years

## Design Documents

Detailed design docs are in `docs/design/`:

| Doc | Topic |
|-----|-------|
| `01_project_overview.md` | Scope, key decisions, constraints |
| `02_architecture.md` | Component diagrams and data flow |
| `03_data_model.md` | Database schema and node scoring formula |
| `04_ingest_pipeline.md` | Ingestion workflow details |
| `05_retrieval_pipeline.md` | Query and retrieval strategy |
| `06_api_contract.md` | REST API specification |
| `07_frontend_adaptation.md` | Frontend integration notes |
| `08_implementation_plan.md` | Phased build plan |
