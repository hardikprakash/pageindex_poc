# PageIndex PoC: Financial Filing Q&A System

A re-implementation of [PageIndex](https://github.com/getmetal/pageindex) for querying and analyzing financial filings across multiple companies and years using semantic tree structures and hybrid retrieval.

## Overview

This project implements a vectorless, reasoning-based RAG system specifically designed for multi-year, multi-company financial documents (e.g., Form 20-F filings). Instead of traditional vector similarity search, it leverages **PageIndex's semantic tree structures** combined with **LLM-powered tree navigation** for accurate, cited answers.

### Key Features

- 📄 **Multi-document support**: Ingest and query across multiple Form 20-F filings from different companies and years
- 🌳 **Semantic tree indexing**: Generates hierarchical document structures with semantic summaries
- 🔍 **Hybrid retrieval**: Combines value-based node scoring with LLM tree search for robust results
- 💾 **Embedding storage**: Optional embeddings (768-dim) for value-based search via Ollama
- 📝 **Cited answers**: LLM generates answers with page/node citations for verification
- ⚡ **CLI ingest pipeline**: Single-document or batch ingestion with metadata auto-detection
- 🧪 **Comprehensive tests**: 56 unit tests covering all core modules
- 🐳 **Docker-ready**: Ollama embeddings service included in docker-compose

## Architecture

### Core Components

```
backend/
├── config.py          # Centralized configuration
├── database.py        # SQLite schema and connection
├── models.py          # Pydantic schemas
├── llm/
│   └── client.py      # OpenRouter LLM wrapper
├── ingest/
│   ├── metadata.py    # PDF filename parser (TICKER_DOCTYPE_YEAR)
│   ├── chunker.py     # Token-aware text chunking
│   ├── embedder.py    # Ollama embedding client
│   └── pipeline.py    # Full ingest orchestration
└── corpus/
    └── manager.py     # Document CRUD operations
```

### Data Flow

```
PDF → PageIndex Tree Generation → Chunking & Embedding → SQLite Storage
                                           ↓
Query → Value Search + LLM Search → Hybrid Merge → Answer + Citations
```

## Installation

### Prerequisites

- Python 3.9+
- Docker & Docker Compose (for Ollama embeddings)
- OpenRouter API key

### Setup

1. **Clone and setup virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   pip install pytest pytest-asyncio  # For testing
   ```

3. **Start Ollama service:**
   ```bash
   docker-compose up -d
   ```
   This starts Ollama on port 11435 with `nomic-embed-text-v2-moe` model pre-loaded.

4. **Configure environment:**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` with your OpenRouter API key:
   ```
   OPENAI_API_KEY=sk-or-v1-xxxxx
   OPENAI_BASE_URL=https://openrouter.ai/api/v1
   LLM_MODEL=openai/gpt-5.2
   ```

## Usage

### Ingestion Pipeline

Ingest financial PDFs with automatic metadata detection from filenames.

**Single document:**
```bash
python -m scripts.ingest --pdf data/INFY_20F_2022.pdf --company "Infosys"
```

**Batch ingestion:**
```bash
python -m scripts.ingest --dir data/pdfs/ --company-map mapping.json
```

Where `mapping.json`:
```json
{
  "INFY_20F_2022.pdf": "Infosys",
  "INFY_20F_2023.pdf": "Infosys",
  "TCS_20F_2022.pdf": "Tata Consultancy Services"
}
```

**Force re-ingestion** (skip duplicate check):
```bash
python -m scripts.ingest --pdf data/INFY_20F_2022.pdf --company "Infosys" --force
```

### Filename Format

PDFs must follow the naming convention: `TICKER_DOCTYPE_YEAR.pdf`

Examples:
- `INFY_20F_2022.pdf` → Infosys, Form 20-F, 2022
- `TCS_10K_2023.pdf` → TCS, Form 10-K, 2023

### Query Interface

(Implementation pending - Phase 5 in roadmap)

```bash
python -m scripts.query "What was the revenue in 2022?"
```

## Testing

Run the comprehensive test suite:

```bash
# All tests
python -m pytest tests/ -v

# Specific module
python -m pytest tests/test_pipeline.py -v

# With coverage
python -m pytest tests/ --cov=backend
```

### Test Coverage

- **test_metadata.py** (12 tests): Filename parsing, normalization, edge cases
- **test_chunker.py** (8 tests): Token counting, splitting, overlap handling
- **test_database.py** (5 tests): Schema, CRUD, constraints
- **test_corpus.py** (12 tests): Document operations, tree retrieval
- **test_embedder.py** (3 tests): Embedding generation, batching
- **test_pipeline.py** (16 tests): End-to-end ingest flow with mocked externals

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | (required) | OpenRouter API key |
| `OPENAI_BASE_URL` | https://openrouter.ai/api/v1 | LLM endpoint |
| `LLM_MODEL` | openai/gpt-5.2 | Model to use |
| `OLLAMA_URL` | http://localhost:11435 | Ollama service endpoint |
| `OLLAMA_MODEL` | nomic-embed-text-v2-moe | Embedding model |
| `DB_PATH` | data/pageindex.db | SQLite database location |
| `CHUNK_MAX_TOKENS` | 512 | Max tokens per chunk |
| `CHUNK_OVERLAP_TOKENS` | 64 | Token overlap between chunks |
| `CHUNK_MIN_TOKENS` | 32 | Minimum chunk size |

### Database Schema

Three-table design optimized for retrieval:

- **documents**: Metadata (ticker, fiscal_year, doc_type, company_name, page_count)
- **trees**: Full PageIndex tree JSON + derived structures (tree_no_text, node_map)
- **chunks**: Searchable text chunks with 768-dim embeddings (BLOB)

Unique constraint on `(ticker, fiscal_year, doc_type)` prevents duplicates.

## Project Structure

```
pageindex_poc/
├── backend/                 # Core backend modules
├── scripts/
│   └── ingest.py           # Ingestion CLI
├── tests/                  # Unit tests (56 tests)
├── docs/
│   ├── context/            # Reference materials
│   └── design/             # Design documents (8 docs)
├── data/
│   ├── uploads/            # Ingested PDFs
│   └── pageindex.db        # SQLite database
├── docker-compose.yaml     # Ollama service
├── requirements.txt        # Python dependencies
└── README.md               # This file
```

## Development Roadmap

### ✅ Completed
- [x] Design & architecture documentation
- [x] Ingestion pipeline (PDF → tree → chunks → embeddings → SQLite)
- [x] Metadata parser (TICKER_DOCTYPE_YEAR format)
- [x] Token-aware chunker with overlap
- [x] Ollama embeddings integration
- [x] SQLite database with cascading deletes
- [x] CLI ingestion script (single & batch)
- [x] 56 comprehensive unit tests (100% passing)

### 🚧 In Progress / Planned
- [ ] Retrieval pipeline (value search + LLM tree search)
- [ ] Hybrid merge & deduplication
- [ ] Answer generation with citations
- [ ] FastAPI backend endpoints (`/corpus`, `/ingest`, `/query`)
- [ ] Frontend integration (Streamlit)
- [ ] End-to-end testing with real Form 20-F filings

## Common Operations

### Resetting Data & Ingesting New Documents

To wipe all ingested data and start fresh with new documents:

```bash
# 1. Delete the SQLite database and uploaded PDFs
rm -f data/pageindex.db data/pageindex.db-wal data/pageindex.db-shm
rm -rf data/uploads/

# 2. Ingest new documents (the database is auto-created on first ingest)
python -m scripts.ingest --dir data/new_pdfs/ --company-map data/company_map.json
```

To selectively remove a single document (its tree and chunks are cascade-deleted automatically):

```python
from backend.corpus.manager import list_documents, delete_document

# List all ingested documents to find the doc_id
for doc in list_documents():
    print(doc["id"], doc["ticker"], doc["fiscal_year"], doc["doc_type"])

# Delete a specific document by ID
delete_document("the-doc-id-here")
```

To replace a specific document without touching the rest, use `--force` to overwrite the existing entry matching the same `(ticker, fiscal_year, doc_type)`:

```bash
python -m scripts.ingest --pdf data/INFY_20F_2022.pdf --company "Infosys Ltd" --force
```

### Re-embedding with a Different Model

Embeddings are generated during ingestion. To switch to a different embedding model, you need to update the config and re-ingest all documents so that every chunk uses the same model's embeddings.

**Step 1 — Update embedding config** in your `.env` file:

```bash
# Change model and dimension to match the new model
EMBEDDING_MODEL=mxbai-embed-large       # or any Ollama-supported model
EMBEDDING_DIM=1024                       # must match the model's output dimension
```

**Step 2 — Ensure the new model is pulled in Ollama:**

```bash
# Pull the model into Ollama
docker exec ollama-pageindex ollama pull mxbai-embed-large

# Verify it's available
curl http://localhost:11435/api/tags
```

**Step 3 — Wipe and re-ingest everything** (embeddings are stored per-chunk, so a full re-ingest is required):

```bash
# Delete existing data
rm -f data/pageindex.db data/pageindex.db-wal data/pageindex.db-shm

# Re-ingest all documents (trees are regenerated + re-embedded with new model)
python -m scripts.ingest --dir data/pdfs/ --company-map data/company_map.json
```

> **Note:** If you only want to re-embed without regenerating the PageIndex trees (which is the expensive LLM step), that workflow is not yet supported but is planned for a future `--re-embed-only` flag.

**Common embedding models available via Ollama:**

| Model | Dimensions | Notes |
|-------|-----------|-------|
| `nomic-embed-text-v2-moe` | 768 | Default — good balance of quality & speed |
| `mxbai-embed-large` | 1024 | Higher quality, slightly slower |
| `all-minilm` | 384 | Fastest, lower quality |
| `snowflake-arctic-embed` | 1024 | Strong multilingual support |

## Troubleshooting

### Ollama Connection Issues
```bash
# Check if Ollama is running
curl http://localhost:11435/api/tags

# Restart Ollama service
docker-compose restart ollama-pageindex
```

### Database Corruption
```bash
# Reset database (WARNING: Deletes all data)
rm data/pageindex.db
python -m scripts.ingest --pdf data/sample.pdf --company "Test"
```

### OpenRouter API Errors
- Verify API key in `.env` (format: `sk-or-v1-...`)
- Check account has sufficient credits
- Ensure base URL is `https://openrouter.ai/api/v1`

## Design References

See `docs/design/` for detailed documentation:
- `01_project_overview.md` - Scope and key decisions
- `02_architecture.md` - Component diagrams and flow
- `03_data_model.md` - Database schema and node scoring formulas
- `04_ingest_pipeline.md` - Ingestion workflow details
- `05_retrieval_pipeline.md` - Query and retrieval strategy
- `06_api_contract.md` - REST API specification
- `07_frontend_adaptation.md` - Frontend integration notes
- `08_implementation_plan.md` - Phased development plan

## License

[Specify your license here]

## Contributing

[Contribution guidelines]

## Contact

For questions or issues, please open an issue or contact the development team.
