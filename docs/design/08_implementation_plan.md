# Implementation Plan — Phased Build Order

## 1. Phases Overview

| Phase | Name | Deliverable | Est. Effort |
|---|---|---|---|
| 0 | Infrastructure Setup | Docker, env, DB init, skeleton | 1–2 hours |
| 1 | Ingest Pipeline | PDF → tree → chunks → embeddings → SQLite | 4–6 hours |
| 2 | Retrieval — Value-Based Search | Embed query → cosine sim → node ranking | 2–3 hours |
| 3 | Retrieval — LLM Tree Search | Prompt LLM with tree → node selection | 2–3 hours |
| 4 | Retrieval — Hybrid Merge + Answer Gen | Combine searches, generate cited answer | 3–4 hours |
| 5 | API Layer | FastAPI endpoints matching frontend contract | 2–3 hours |
| 6 | Frontend Adaptation | Minor cosmetic tweaks to Streamlit app | 1 hour |
| 7 | End-to-End Testing | Ingest real 20-F filings, run queries | 2–3 hours |

**Total estimated:** ~16–25 hours

---

## 2. Phase Details

### Phase 0: Infrastructure Setup

**Goal:** Project skeleton, Docker services running, database created.

- [ ] Create `backend/` package structure:
  ```
  backend/
    __init__.py
    main.py              # FastAPI app
    config.py             # env vars, constants
    database.py           # SQLite connection, schema init
    ingest/
      __init__.py
      pipeline.py
      chunker.py
      embedder.py
      metadata.py
    retrieval/
      __init__.py
      pipeline.py
      query_decomposer.py
      doc_selector.py
      value_search.py
      llm_search.py
      hybrid_merge.py
      context_extractor.py
      answer_generator.py
      confidence.py
    corpus/
      __init__.py
      manager.py
    llm/
      __init__.py
      client.py
  ```
- [ ] Update `docker-compose.yaml` to auto-pull `nomic-embed-text-v2-moe`
- [ ] Create `backend/database.py` with schema migration
- [ ] Create `backend/config.py` reading env vars
- [ ] Create `.env.example` template
- [ ] Update `requirements.txt` with `fastapi`, `uvicorn`, `httpx`, `numpy`
- [ ] Verify Ollama is reachable and model works

### Phase 1: Ingest Pipeline

**Goal:** Upload a PDF → full tree with embeddings stored in SQLite.

- [ ] `backend/ingest/metadata.py` — filename parser + auto-detection
- [ ] `backend/ingest/pipeline.py` — orchestrate:
  1. Save PDF to disk
  2. Call `pageindex.page_index_main()` with configured opts
  3. Build node_map, tree_no_text
  4. Chunk node texts
  5. Embed chunks via Ollama
  6. Write all to SQLite
- [ ] `backend/ingest/chunker.py` — token-based text chunking
- [ ] `backend/ingest/embedder.py` — Ollama HTTP client
- [ ] Test with a small PDF (< 20 pages) end-to-end
- [ ] Test with a real 20-F filing

### Phase 2: Value-Based Search

**Goal:** Given a query, return ranked nodes by embedding similarity.

- [ ] `backend/retrieval/value_search.py`:
  - Embed query via Ollama
  - Load chunk embeddings from SQLite
  - Compute cosine similarity
  - Aggregate to node scores using PageIndex formula
  - Return top-K nodes
- [ ] Unit test with known document + known query

### Phase 3: LLM Tree Search

**Goal:** Given a query, use LLM reasoning to select relevant nodes.

- [ ] `backend/llm/client.py` — async OpenRouter wrapper
- [ ] `backend/retrieval/llm_search.py`:
  - Load tree_no_text from SQLite
  - Format prompt with tree structure
  - Parse LLM JSON response → node_id list
  - Handle malformed LLM responses gracefully
- [ ] Test with real tree structure

### Phase 4: Hybrid Merge + Answer Generation

**Goal:** Combine both search legs, extract context, generate answer.

- [ ] `backend/retrieval/hybrid_merge.py` — deduplicated merge
- [ ] `backend/retrieval/context_extractor.py` — fetch node text by IDs
- [ ] `backend/retrieval/query_decomposer.py` — LLM-based decomposition
- [ ] `backend/retrieval/doc_selector.py` — SQL metadata filter
- [ ] `backend/retrieval/answer_generator.py` — answer + citations prompt
- [ ] `backend/retrieval/confidence.py` — scoring logic
- [ ] `backend/retrieval/pipeline.py` — orchestrate full flow
- [ ] Test multi-document query end-to-end

### Phase 5: API Layer

**Goal:** FastAPI app serving all endpoints.

- [ ] `backend/main.py`:
  - `GET /corpus`
  - `POST /ingest`
  - `POST /query`
  - `GET /health`
  - CORS middleware
  - Startup event (DB init, Ollama check)
- [ ] `backend/corpus/manager.py` — list/get/delete documents
- [ ] Pydantic models for request/response validation
- [ ] Test all endpoints with curl / httpx

### Phase 6: Frontend Adaptation

**Goal:** Streamlit app works with the new backend.

- [ ] Update about text to reference PageIndex
- [ ] Verify all pages render correctly with backend responses
- [ ] Test ingest flow through UI
- [ ] Test query flow through UI

### Phase 7: End-to-End Testing

**Goal:** Full PoC validated with real filings.

- [ ] Ingest 8 real 20-F filings (2 companies × 4 years)
- [ ] Run diverse query types:
  - Single-document factual ("What was AAPL revenue in 2023?")
  - Cross-year comparison ("How did revenue change 2020–2023?")
  - Cross-company comparison ("Compare AAPL vs TSM margins")
  - Complex multi-hop ("What risks does AAPL mention that TSM doesn't?")
- [ ] Verify citations point to correct pages
- [ ] Verify confidence scores are reasonable
- [ ] Document any issues or limitations

---

## 3. Dependencies Between Phases

```
Phase 0 ──→ Phase 1 ──→ Phase 2 ──→ Phase 4 ──→ Phase 5 ──→ Phase 6 ──→ Phase 7
                    └──→ Phase 3 ──┘
```

Phases 2 and 3 are independent of each other and can be built in parallel.

---

## 4. Final Directory Structure

```
pageindex_poc/
├── .env                          # API keys (gitignored)
├── .env.example                  # template
├── docker-compose.yaml           # Ollama service
├── requirements.txt              # all Python deps
├── run_pageindex.py              # CLI tool (existing)
├── data/
│   ├── uploads/                  # ingested PDFs
│   └── pageindex.db              # SQLite database
├── backend/
│   ├── __init__.py
│   ├── main.py                   # FastAPI app
│   ├── config.py
│   ├── database.py
│   ├── models.py                 # Pydantic schemas
│   ├── ingest/
│   │   ├── __init__.py
│   │   ├── pipeline.py
│   │   ├── chunker.py
│   │   ├── embedder.py
│   │   └── metadata.py
│   ├── retrieval/
│   │   ├── __init__.py
│   │   ├── pipeline.py
│   │   ├── query_decomposer.py
│   │   ├── doc_selector.py
│   │   ├── value_search.py
│   │   ├── llm_search.py
│   │   ├── hybrid_merge.py
│   │   ├── context_extractor.py
│   │   ├── answer_generator.py
│   │   └── confidence.py
│   ├── corpus/
│   │   ├── __init__.py
│   │   └── manager.py
│   └── llm/
│       ├── __init__.py
│       └── client.py
├── frontend/
│   ├── __init__.py
│   └── app.py                    # Streamlit (minimal changes)
├── pageindex/                    # existing package (unchanged)
│   ├── __init__.py
│   ├── config.yaml
│   ├── page_index.py
│   ├── page_index_md.py
│   └── utils.py
├── docs/
│   ├── context/                  # PageIndex documentation
│   └── design/                   # these design documents
└── logs/                         # pageindex processing logs
```
