# Data Model — SQLite Schema & Tree Storage

## 1. Overview

All persistent state lives in a single SQLite database (`data/pageindex.db`).
Three tables cover the full lifecycle: document metadata, tree structures,
and embedding chunks for the value-based search leg.

---

## 2. Schema

### 2.1 `documents` — Corpus Metadata

```sql
CREATE TABLE documents (
    id              TEXT PRIMARY KEY,          -- UUID
    company         TEXT NOT NULL,             -- e.g. "Apple Inc."
    ticker          TEXT NOT NULL,             -- e.g. "AAPL"
    fiscal_year     INTEGER NOT NULL,          -- e.g. 2023
    doc_type        TEXT NOT NULL DEFAULT '20-F',  -- "20-F", "10-K", etc.
    filename        TEXT NOT NULL,             -- original uploaded filename
    page_count      INTEGER,                  -- total PDF pages
    total_tokens    INTEGER,                  -- total token count
    node_count      INTEGER DEFAULT 0,        -- number of tree nodes
    chunk_count     INTEGER DEFAULT 0,        -- number of embedding chunks
    status          TEXT NOT NULL DEFAULT 'processing',  -- processing | completed | failed
    error_message   TEXT,                     -- if status = failed
    ingest_timestamp TEXT NOT NULL,            -- ISO 8601
    UNIQUE(ticker, fiscal_year, doc_type)     -- prevent duplicate filings
);
```

### 2.2 `trees` — PageIndex Tree Structures

Stores the complete tree JSON produced by `page_index_main()`, plus the
per-node text blobs for retrieval.

```sql
CREATE TABLE trees (
    doc_id          TEXT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
    tree_json       TEXT NOT NULL,             -- full tree structure (JSON)
    tree_no_text    TEXT NOT NULL,             -- tree without node text (for LLM prompts)
    node_map_json   TEXT NOT NULL              -- flat {node_id → {title, page_index, text, summary}} map
);
```

**Design notes:**

- `tree_json` stores the complete output from `page_index_main()` including
  node text, summaries, and node IDs — the canonical source of truth.
- `tree_no_text` is a pre-computed copy with `text` fields stripped, used
  when prompting the LLM for tree search (fits in context window).
- `node_map_json` is a flat dict keyed by `node_id` for O(1) node lookups
  during context extraction. Equivalent to `utils.create_node_mapping()`.

### 2.3 `chunks` — Embedding Chunks for Value-Based Search

Each tree leaf node is split into one or more text chunks. Each chunk has an
associated embedding vector stored as a BLOB.

```sql
CREATE TABLE chunks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id          TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    node_id         TEXT NOT NULL,             -- parent node's node_id (e.g. "0007")
    chunk_index     INTEGER NOT NULL,          -- 0-based index within the node
    content         TEXT NOT NULL,             -- raw chunk text
    token_count     INTEGER NOT NULL,          -- tokens in this chunk
    start_page      INTEGER,                  -- page range start
    end_page        INTEGER,                  -- page range end
    embedding       BLOB NOT NULL,            -- 768-d float32 vector (768 × 4 = 3072 bytes)
    UNIQUE(doc_id, node_id, chunk_index)
);

CREATE INDEX idx_chunks_doc ON chunks(doc_id);
CREATE INDEX idx_chunks_node ON chunks(doc_id, node_id);
```

---

## 3. Vector Storage Strategy

Since this is a PoC with ~8 documents (~800–2,400 pages), we store embedding
vectors directly in SQLite as BLOBs (`numpy.ndarray.tobytes()`).

**At query time:**

1. Load all chunk embeddings for the selected documents into memory.
2. Compute cosine similarity with the query embedding using NumPy.
3. Score nodes by aggregating their chunk similarities (see §5).

This avoids adding a vector DB dependency. For ~10k chunks at 768-d, loading
all vectors takes ~30 MB of RAM and cosine similarity runs in <100ms.

---

## 4. Tree Structure In-Memory Representation

When loaded for retrieval, the tree is used in two forms:

### 4.1 Full Tree (for context extraction)

```python
{
    "doc_name": "AAPL_2023_20F",
    "structure": [
        {
            "title": "Cover Page",
            "node_id": "0000",
            "start_index": 1,
            "end_index": 2,
            "summary": "...",
            "text": "...",           # full text of this node's pages
            "nodes": [...]           # children
        },
        ...
    ]
}
```

### 4.2 Lightweight Tree (for LLM tree search prompts)

```python
[
    {
        "title": "Cover Page",
        "node_id": "0000",
        "summary": "...",
        "nodes": [
            {
                "title": "Business Overview",
                "node_id": "0001",
                "summary": "...",
                "nodes": [...]
            }
        ]
    }
]
```

No `text`, `start_index`, or `end_index` — keeps the prompt compact.

### 4.3 Node Map (for O(1) lookups)

```python
{
    "0000": {
        "title": "Cover Page",
        "node_id": "0000",
        "start_index": 1,
        "end_index": 2,
        "text": "...",
        "summary": "..."
    },
    "0001": { ... },
    ...
}
```

Built once during ingest via `utils.structure_to_list()` then
converted to a dict keyed by `node_id`.

---

## 5. Node Scoring Formula (Value-Based Search)

From the PageIndex hybrid tree search documentation:

$$
\text{NodeScore} = \frac{1}{\sqrt{N + 1}} \sum_{n=1}^{N} \text{ChunkScore}(n)
$$

Where:
- $N$ = number of chunks belonging to the node
- $\text{ChunkScore}(n)$ = cosine similarity between query embedding and
  chunk $n$'s embedding

This formula rewards nodes with multiple relevant chunks while applying
diminishing returns to prevent large nodes from dominating.

---

## 6. Chunking Strategy

Each node's text is split into chunks for embedding:

| Parameter | Value | Rationale |
|---|---|---|
| Max tokens per chunk | 512 | Fits `nomic-embed-text-v2-moe` context |
| Overlap tokens | 64 | Continuity across chunk boundaries |
| Min chunk tokens | 32 | Skip near-empty fragments |

Chunks are created from **all** tree nodes (not just leaves), since parent
nodes may contain introductory text that isn't covered by children.
