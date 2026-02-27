# Project Overview — PageIndex Financial Filings Agent

## 1. Purpose

A production-ready PoC that lets users **ask natural-language questions** across
a corpus of 20-F filings (multiple companies, multiple years) and receive
**cited, traceable answers** powered by the open-source PageIndex tree-generation
package and a custom hybrid retrieval + answer-generation pipeline.

The PageIndex **Chat API is not used** anywhere. Instead, we:

1. Use the local `pageindex` package to generate semantic tree structures from
   uploaded PDFs (with our own LLM key via OpenRouter).
2. Implement our own **hybrid tree search** (LLM reasoning + embedding value
   search) to retrieve relevant tree nodes.
3. Feed retrieved context to an LLM for **answer synthesis with citations**.
4. Expose everything via a **FastAPI backend** that the existing Streamlit
   frontend consumes unmodified.

---

## 2. Scope (PoC Boundaries)

| In scope | Out of scope |
|---|---|
| Generic metadata model (company, ticker, year, doc type) | Hard-coding any specific company |
| PDF upload → tree generation → storage | Non-PDF inputs (HTML, Excel) |
| Hybrid tree search (LLM + embedding) | Fine-tuned embedding models |
| Multi-document retrieval (filter by metadata) | Cross-lingual retrieval |
| Streaming answer generation with citations | User auth / multi-tenant |
| Corpus management UI (existing Streamlit) | Advanced analytics dashboards |
| SQLite storage for trees + metadata | Cloud-hosted DB |
| Ollama `nomic-embed-text-v2-moe` for embeddings | OpenAI embeddings |

---

## 3. Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| LLM provider | OpenRouter (`openai/gpt-5.2`) | Already patched into the pageindex package |
| Embedding model | Ollama `nomic-embed-text-v2-moe` (768-d) | Local, free, docker-compose ready |
| Tree generation | Local `pageindex` package (`page_index_main`) | Uses our own LLM key; no PageIndex API |
| Storage | SQLite (single file, zero-infra) | Sufficient for PoC scale |
| Metadata model | Generic: `{company, ticker, fiscal_year, doc_type}` | Filename convention for auto-extraction |
| Frontend | Existing Streamlit app (unmodified) | Thin client; talks to FastAPI |

---

## 4. Document Scale

- **Companies**: configurable (PoC targets ~2)
- **Years per company**: ~4 (4 × 20-F filings per company)
- **Total documents**: ~8 PDFs
- **Pages per document**: typically 100–300+
- **Total corpus**: ~800–2,400 pages

---

## 5. Filename Convention (suggested)

To allow automatic metadata extraction at ingest time:

```
<TICKER>_<DOCTYPE>_<YEAR>.pdf
```

Examples:
```
INFY_20F_2022.pdf
TSM_20F_2021.pdf
```

The user can also manually specify metadata during upload via the frontend form.

---

## 6. Document Map

```
docs/design/
  01_project_overview.md        ← this file
  02_architecture.md            ← system architecture & component diagram
  03_data_model.md              ← SQLite schema, tree storage, embeddings
  04_ingest_pipeline.md         ← PDF → tree → storage workflow
  05_retrieval_pipeline.md      ← hybrid tree search & answer generation
  06_api_contract.md            ← FastAPI endpoints (matching frontend)
  07_frontend_adaptation.md     ← changes needed for Streamlit app
  08_implementation_plan.md     ← phased build order & task list
```
