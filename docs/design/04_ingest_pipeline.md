# Ingest Pipeline — PDF → Tree → Searchable Storage

## 1. Overview

The ingest pipeline transforms an uploaded PDF financial filing into a
fully searchable representation: a PageIndex tree structure with node text,
summaries, and pre-computed embedding vectors.

```
PDF + metadata ──→ Tree Generation ──→ Text Enrichment ──→ Chunking ──→ Embedding ──→ SQLite
```

---

## 2. Pipeline Steps

### Step 1: Receive Upload

**Trigger:** `POST /ingest` with a PDF file + metadata form fields.

```python
# Expected form fields:
# - file: UploadFile (PDF)
# - company: str
# - ticker: str
# - fiscal_year: int
# - doc_type_hint: str (optional; defaults to "20-F")
```

**Auto-detection from filename** (fallback if metadata fields are empty):

```
Pattern: <TICKER>_<DOCTYPE>_<YEAR>.pdf
Example: INFY_20F_2022.pdf → ticker="INFY", doc_type="20-F", fiscal_year=2022
```

**Actions:**
1. Save PDF to `data/uploads/<doc_id>.pdf`
2. Create `documents` row with `status = 'processing'`
3. Return `doc_id` immediately; processing continues in background

### Step 2: Generate PageIndex Tree

Uses the existing `pageindex` package with our LLM configuration:

```python
from pageindex import page_index_main, config

opt = config(
    model="openai/gpt-5.2",
    toc_check_page_num=20,
    max_page_num_each_node=10,
    max_token_num_each_node=20000,
    if_add_node_id="yes",
    if_add_node_summary="yes",
    if_add_doc_description="yes",
    if_add_node_text="yes",          # ← IMPORTANT: we need text for retrieval
)

result = page_index_main(pdf_path, opt)
# result = {"doc_name": "...", "doc_description": "...", "structure": [...]}
```

**Key configuration notes:**
- `if_add_node_text="yes"` ensures each node contains the full page text
  for its page range — required for retrieval context extraction.
- `if_add_node_summary="yes"` generates LLM summaries for each node —
  required for the LLM tree search prompt.
- The model is set to `openai/gpt-5.2` via OpenRouter (already patched in
  `utils.py` to use `OPENAI_BASE_URL` and `OPENAI_API_KEY`).

### Step 3: Build Derived Structures

After tree generation, compute the auxiliary structures:

```python
from pageindex.utils import structure_to_list, remove_fields

# 1. Full tree with text (store as-is)
tree_json = result["structure"]

# 2. Tree without text (for LLM prompts)
tree_no_text = remove_fields(tree_json, fields=["text"])

# 3. Flat node map for O(1) lookups
nodes = structure_to_list(tree_json)
node_map = {node["node_id"]: node for node in nodes}
```

### Step 4: Chunk Node Text

Split each node's text into embedding-sized chunks:

```python
def chunk_node_text(text: str, max_tokens: int = 512, overlap: int = 64) -> list[str]:
    """Split text into overlapping chunks by token count."""
    tokens = encoder.encode(text)
    chunks = []
    start = 0
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        chunk_tokens = tokens[start:end]
        chunk_text = encoder.decode(chunk_tokens)
        if len(chunk_tokens) >= 32:  # skip tiny fragments
            chunks.append(chunk_text)
        start += max_tokens - overlap
    return chunks
```

**Which nodes to chunk:**
- All nodes (leaves and internal) — internal nodes may contain introductory
  text (e.g. section headers, preambles) not duplicated in children.
- To avoid double-embedding shared text, each node is chunked only using its
  **own prefix text** (text between node start and first child start) plus
  the full text of leaf nodes.

### Step 5: Generate Embeddings

Send chunks to the Ollama container running `nomic-embed-text-v2-moe`:

```python
import httpx
import numpy as np

OLLAMA_URL = "http://localhost:11435"

async def embed_texts(texts: list[str]) -> list[np.ndarray]:
    """Embed a batch of texts using Ollama."""
    resp = await httpx.AsyncClient().post(
        f"{OLLAMA_URL}/api/embed",
        json={"model": "nomic-embed-text-v2-moe", "input": texts},
        timeout=120.0
    )
    resp.raise_for_status()
    return [np.array(e, dtype=np.float32) for e in resp.json()["embeddings"]]
```

**Batching:** Process chunks in batches of 32 to avoid overwhelming Ollama.

### Step 6: Store in SQLite

All data written in a single transaction:

```python
# 1. Update documents row
UPDATE documents SET
    page_count = ?,
    total_tokens = ?,
    node_count = ?,
    chunk_count = ?,
    status = 'completed',
    ingest_timestamp = ?
WHERE id = ?

# 2. Insert tree
INSERT INTO trees (doc_id, tree_json, tree_no_text, node_map_json)
VALUES (?, ?, ?, ?)

# 3. Insert chunks with embeddings
INSERT INTO chunks (doc_id, node_id, chunk_index, content, token_count,
                    start_page, end_page, embedding)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
```

Embeddings are stored as `numpy.ndarray.tobytes()` (768 × 4 = 3,072 bytes
per vector).

---

## 3. Error Handling

| Failure point | Recovery |
|---|---|
| PDF parsing fails | Set `status='failed'`, store error message |
| Tree generation LLM errors | Retry up to 10× (built into pageindex) |
| Ollama embedding timeout | Retry batch up to 3× with backoff |
| SQLite write fails | Roll back transaction, set `status='failed'` |

---

## 4. Ingest Time Estimates

| Step | Estimated time (100-page PDF) |
|---|---|
| Tree generation (LLM calls) | 3–10 minutes |
| Summary generation | 1–3 minutes |
| Chunking | < 5 seconds |
| Embedding (Ollama) | 30–60 seconds |
| SQLite writes | < 1 second |
| **Total** | **~5–15 minutes per document** |

Ingest is intentionally a background process — the API returns immediately
with a `doc_id` and `status: processing`.

---

## 5. Re-ingest / Overwrite

If a document with the same `(ticker, fiscal_year, doc_type)` already exists:
- Return a 409 Conflict by default
- Accept a `?force=true` query param to delete the old document and re-ingest

---

## 6. Module Structure

```
backend/
  ingest/
    __init__.py
    pipeline.py          # orchestrates the full ingest flow
    chunker.py           # text chunking logic
    embedder.py          # Ollama embedding client
    metadata.py          # filename parsing, auto-detection
```
