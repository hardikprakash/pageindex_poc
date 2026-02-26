# Financial Filings Agent — PageIndex PoC

A financial document Q&A agent powered by **PageIndex** reasoning-based RAG.
Upload 20-F / 10-K / annual report PDFs, and ask natural-language questions
with full source citations.

> **Comparison project**: This is a parallel PoC to `gamma_poc` (Graph RAG with
> Neo4j). Both share the same Streamlit UI layout but use different retrieval
> backends — this one uses PageIndex's vectorless, reasoning-based approach.

## Architecture

```
┌─────────────┐      ┌──────────────┐      ┌─────────────────┐
│  Streamlit   │─────▶│   FastAPI     │─────▶│  PageIndex API  │
│  Frontend    │◀─────│   Backend     │◀─────│  (Cloud)        │
└─────────────┘      └──────┬───────┘      └─────────────────┘
                            │
                     ┌──────▼───────┐
                     │  SQLite       │
                     │  (metadata)   │
                     └──────────────┘
```

**Key differences from Graph RAG (gamma_poc):**

| Aspect | gamma_poc (Graph RAG) | pageindex_poc |
|--------|----------------------|---------------|
| Retrieval | Neo4j knowledge graph + vector embeddings | PageIndex tree-structured reasoning-based RAG |
| Ingestion | M1→M5 pipeline (parse, structure, chunk, extract, build graph) | Upload PDF → PageIndex handles everything |
| Dependencies | Neo4j, Ollama, OpenRouter | PageIndex API key only |
| Chunking | Manual 512-token chunks with overlap | No chunking — PageIndex uses hierarchical ToC |
| Embeddings | Local Ollama (nomic-embed-text) | Not needed — PageIndex uses reasoning, not vectors |

## Quick Start

### 1. Get a PageIndex API Key

Sign up at [dash.pageindex.ai](https://dash.pageindex.ai/api-keys) and create an API key.

### 2. Setup

```bash
cd pageindex_poc
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env and add your PAGEINDEX_API_KEY
```

### 3. Ingest Documents

```bash
# Single file
python ingest.py --pdf ./data/AAPL_2023.pdf --company "Apple Inc." --ticker AAPL --fiscal-year 2023

# Directory (auto-infers metadata from TICKER_YEAR.pdf filenames)
python ingest.py --pdf-dir ./data
```

### 4. Run the Application

```bash
# Terminal 1: Start the backend
uvicorn api.main:app --reload --port 8000

# Terminal 2: Start the frontend
streamlit run frontend/app.py
```

Open http://localhost:8501 in your browser.

## Project Structure

```
pageindex_poc/
├── api/
│   ├── main.py              # FastAPI endpoints (/query, /corpus, /ingest)
│   └── models.py            # Pydantic request/response models
├── frontend/
│   └── app.py               # Streamlit UI (Query + Corpus pages)
├── tests/
│   ├── test_metadata_store.py
│   ├── test_ingest.py
│   └── test_api.py
├── config.py                # Centralized configuration
├── metadata_store.py        # SQLite metadata for company/year filtering
├── ingest.py                # CLI ingest with checkpointing
├── requirements.txt
├── docker-compose.yaml      # Placeholder (no local services needed)
├── .env.example
└── README.md
```

## CLI Ingest Options

```
python ingest.py --help

Options:
  --pdf PATH              Single PDF file to ingest
  --pdf-dir PATH          Directory of PDFs to ingest
  --company TEXT           Company name
  --ticker TEXT            Ticker symbol
  --fiscal-year INT        Fiscal year
  --doc-type TEXT          Document type hint
  --poll-timeout INT       Seconds to wait for processing (default: 300)
  --checkpoint-file PATH   Checkpoint file (default: .ingest_checkpoint)
  --reset-checkpoint       Reset checkpoint and re-ingest all
  --skip-checks            Skip service connectivity checks
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/query` | Query documents (non-streaming) |
| `POST` | `/query/stream` | Query documents (SSE streaming) |
| `GET` | `/corpus` | List all ingested documents |
| `POST` | `/ingest` | Upload and ingest a PDF |
| `DELETE` | `/corpus/{doc_id}` | Delete a document |
| `GET` | `/health` | Health check |

## Running Tests

```bash
pytest tests/ -v
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PAGEINDEX_API_KEY` | *(required)* | PageIndex API key |
| `OPENROUTER_API_KEY` | | Optional: for sub-question decomposition |
| `BACKEND_URL` | `http://localhost:8000` | Backend URL for Streamlit |
| `PDF_INPUT_DIR` | `./data` | Default PDF input directory |
| `METADATA_DB_PATH` | `metadata.db` | SQLite metadata database path |
