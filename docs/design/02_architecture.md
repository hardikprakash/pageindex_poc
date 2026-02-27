# Architecture — PageIndex Financial Filings Agent

## 1. High-Level Component Diagram

```
┌────────────────────────────────────────────────────────────────────────┐
│                        User (Browser)                                  │
└────────────────────────┬───────────────────────────────────────────────┘
                         │ HTTP
┌────────────────────────▼───────────────────────────────────────────────┐
│                   Streamlit Frontend (app.py)                          │
│  • Query page     • Corpus management page                             │
└────────────────────────┬───────────────────────────────────────────────┘
                         │ HTTP (REST)
┌────────────────────────▼───────────────────────────────────────────────┐
│                    FastAPI Backend (backend/)                           │
│                                                                        │
│  ┌──────────────┐  ┌───────────────────┐  ┌────────────────────────┐  │
│  │ /ingest      │  │ /query            │  │ /corpus                │  │
│  │ endpoint     │  │ endpoint          │  │ endpoint               │  │
│  └──────┬───────┘  └────────┬──────────┘  └───────────┬────────────┘  │
│         │                   │                         │               │
│  ┌──────▼───────┐  ┌───────▼──────────┐  ┌───────────▼────────────┐  │
│  │ Ingest       │  │ Retrieval        │  │ Corpus                 │  │
│  │ Pipeline     │  │ Pipeline         │  │ Manager                │  │
│  │              │  │                  │  │                        │  │
│  │ • PDF parse  │  │ • Query decomp.  │  │ • List documents       │  │
│  │ • Tree gen   │  │ • Doc selection  │  │ • Get metadata         │  │
│  │ • Chunk+Embed│  │ • Hybrid search  │  │ • Delete document      │  │
│  │ • Store      │  │ • Answer gen     │  │                        │  │
│  └──────┬───────┘  └──┬──────┬────────┘  └───────────┬────────────┘  │
│         │             │      │                        │               │
│         └─────────────┼──────┼────────────────────────┘               │
│                       │      │                                        │
│              ┌────────▼──┐ ┌─▼─────────────┐                         │
│              │ LLM Client│ │ Embedding      │                         │
│              │ (OpenRouter│ │ Client         │                         │
│              │  gpt-5.2) │ │ (Ollama local) │                         │
│              └───────────┘ └───────────────┘                         │
└────────────────────────────────────────────────────────────────────────┘
                         │
              ┌──────────▼──────────┐
              │    SQLite Database   │
              │ • documents table    │
              │ • trees table        │
              │ • chunks table       │
              │ • embeddings (BLOB)  │
              └─────────────────────┘
```

## 2. Component Responsibilities

### 2.1 Streamlit Frontend (`frontend/app.py`)

Existing thin client — mostly unchanged. Sends HTTP requests to FastAPI.

| Page | Backend calls |
|---|---|
| Query | `POST /query` |
| Corpus → list | `GET /corpus` |
| Corpus → ingest | `POST /ingest` |

### 2.2 FastAPI Backend (`backend/`)

Central orchestrator. Stateless request handlers that delegate to pipeline modules.

### 2.3 Ingest Pipeline (`backend/ingest/`)

Handles the full lifecycle from PDF upload to searchable storage:

1. **Receive PDF** + metadata (company, ticker, year, doc_type)
2. **Generate PageIndex tree** via `pageindex.page_index_main()`
3. **Add text to nodes** (the tree already supports `if_add_node_text`)
4. **Chunk nodes** for embedding (leaf-node text, split by token limit)
5. **Generate embeddings** via Ollama `nomic-embed-text-v2-moe`
6. **Store** tree JSON, metadata, chunks + embeddings in SQLite

### 2.4 Retrieval Pipeline (`backend/retrieval/`)

Implements hybrid tree search as described in PageIndex docs:

1. **Query decomposition** — break complex questions into sub-queries
2. **Document selection** — use metadata filters (company, year) + SQL-like selection
3. **Hybrid tree search** (per selected document):
   - **Value-based search**: embed query → cosine similarity against chunk embeddings → score nodes
   - **LLM-based tree search**: prompt LLM with tree structure (summaries) to reason about relevant nodes
   - **Merge** results into a deduplicated priority queue
4. **Context extraction** — fetch full text of selected nodes
5. **Answer generation** — prompt LLM with retrieved context + original question
6. **Citation construction** — map answer claims back to source nodes/pages

### 2.5 Corpus Manager (`backend/corpus/`)

CRUD operations on the document store:
- List all documents (with metadata + summary stats)
- Get document detail (tree structure, chunk count)
- Delete a document and its associated data

### 2.6 LLM Client (`backend/llm/`)

Thin wrapper around the OpenAI client, configured for OpenRouter:

```python
client = openai.AsyncOpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)
# Model: openai/gpt-5.2
```

### 2.7 Embedding Client (`backend/embeddings/`)

Calls the Ollama container for embedding generation:

```python
import httpx

async def embed(texts: list[str]) -> list[list[float]]:
    resp = await httpx.post(
        "http://localhost:11435/api/embed",
        json={"model": "nomic-embed-text-v2-moe", "input": texts}
    )
    return resp.json()["embeddings"]
```

Embedding dimension: **768**.

## 3. Infrastructure

```
docker-compose.yaml
├── ollama-pageindex       (GPU-enabled, port 11435)
│   └── model: nomic-embed-text-v2-moe
│
├── (Optional future: backend service)
└── (Optional future: frontend service)
```

For the PoC, the FastAPI backend and Streamlit frontend run directly on the host.
Only Ollama runs in Docker.

## 4. Data Flow Summary

### Ingest Flow
```
PDF file + metadata
  → pageindex.page_index_main() [tree generation, uses OpenRouter LLM]
  → Add text to tree nodes
  → Split leaf nodes into chunks
  → Ollama embed chunks → 768-d vectors
  → Store in SQLite (document, tree JSON, chunks, embeddings)
```

### Query Flow
```
User question + filters (companies, years)
  → Query decomposition (LLM)
  → Select relevant documents (metadata SQL filter)
  → For each document:
      ├── Value-based search (embed query → cosine sim → node scores)
      └── LLM tree search (reason over tree summaries → node list)
      → Merge into priority queue (deduplicated)
  → Extract full text from top-K nodes
  → Generate answer with citations (LLM)
  → Return {answer, citations, confidence}
```
