# Retrieval Pipeline — Hybrid Tree Search & Answer Generation

## 1. Overview

The retrieval pipeline implements the full workflow from user question to
cited answer, following the PageIndex hybrid tree search approach:

```
User Query + Filters
  → Query Decomposition
  → Document Selection (metadata filter)
  → Per-Document Hybrid Tree Search
      ├── Value-Based Search (embedding similarity → node scores)
      └── LLM-Based Tree Search (reasoning over tree summaries → node list)
      → Merge into Priority Queue
  → Context Extraction (fetch node text)
  → Answer Generation (LLM with citations)
  → Response Assembly
```

---

## 2. Step-by-Step

### Step 1: Query Decomposition

Complex financial questions often span multiple dimensions (e.g. "How did
AAPL's revenue compare to TSM's in 2022 and 2023?"). We decompose such
questions into atomic sub-queries.

```python
decomposition_prompt = """
You are given a user question about financial filings.
Break it into independent sub-questions that can each be answered from a
single document section. If the question is already atomic, return it as-is.

Question: {query}

Return JSON:
{{
    "sub_questions": [
        {{
            "question": "<atomic sub-question>",
            "target_company": "<company/ticker or null>",
            "target_year": <year or null>
        }},
        ...
    ]
}}
"""
```

If the user has applied filters (companies, years) in the frontend sidebar,
those are used as hard constraints on document selection.

### Step 2: Document Selection

For each sub-query, select candidate documents:

```sql
SELECT id, company, ticker, fiscal_year, doc_type
FROM documents
WHERE status = 'completed'
  AND (ticker IN (?, ?) OR ? IS NULL)   -- company filter
  AND (fiscal_year IN (?, ?) OR ? IS NULL)  -- year filter
```

If the sub-query has `target_company` or `target_year` from decomposition,
further narrow the set.

### Step 3: Hybrid Tree Search (per document)

This is the core retrieval mechanism, run **in parallel** for each selected
document. It combines two complementary search strategies:

#### 3a. Value-Based Search (embedding leg)

Fast, recall-oriented. Uses pre-computed chunk embeddings.

```python
async def value_based_search(query: str, doc_id: str, top_k: int = 20):
    # 1. Embed the query
    query_embedding = await embed_texts([query])

    # 2. Load all chunk embeddings for this document
    chunks = db.get_chunks(doc_id)  # → list of (node_id, embedding_blob)

    # 3. Cosine similarity
    scores = cosine_similarity(query_embedding, chunk_embeddings)

    # 4. Aggregate to node scores using the PageIndex formula
    node_scores = {}
    for chunk, score in zip(chunks, scores):
        node_id = chunk.node_id
        node_scores.setdefault(node_id, []).append(score)

    # NodeScore = (1 / sqrt(N + 1)) * sum(chunk_scores)
    for node_id, chunk_scores in node_scores.items():
        N = len(chunk_scores)
        node_scores[node_id] = sum(chunk_scores) / math.sqrt(N + 1)

    # 5. Return top-K nodes by score
    return sorted(node_scores.items(), key=lambda x: -x[1])[:top_k]
```

#### 3b. LLM-Based Tree Search (reasoning leg)

Deep, precision-oriented. Uses the LLM to reason over the tree structure.

```python
async def llm_tree_search(query: str, doc_id: str):
    tree_no_text = db.get_tree_no_text(doc_id)

    search_prompt = f"""
    You are given a question and a tree structure of a financial document.
    Each node contains a node id, title, and summary.
    Find all nodes likely to contain the answer.

    Question: {query}

    Document tree structure:
    {json.dumps(tree_no_text, indent=2)}

    Reply in JSON:
    {{
        "thinking": "<reasoning about which nodes are relevant>",
        "node_list": ["node_id_1", "node_id_2", ...]
    }}
    """

    result = await call_llm(search_prompt)
    return json.loads(result)["node_list"]
```

#### 3c. Hybrid Merge

Combine results from both legs into a deduplicated priority queue:

```python
async def hybrid_tree_search(query: str, doc_id: str):
    # Run both searches in parallel
    value_results, llm_results = await asyncio.gather(
        value_based_search(query, doc_id),
        llm_tree_search(query, doc_id)
    )

    # Merge into ordered set (preserve insertion order, deduplicate)
    seen = set()
    merged_nodes = []

    # LLM results first (higher precision)
    for node_id in llm_results:
        if node_id not in seen:
            seen.add(node_id)
            merged_nodes.append(node_id)

    # Then value-based results (higher recall)
    for node_id, score in value_results:
        if node_id not in seen:
            seen.add(node_id)
            merged_nodes.append(node_id)

    return merged_nodes
```

### Step 4: Context Extraction

Fetch full text for the selected nodes:

```python
def extract_context(doc_id: str, node_ids: list[str], max_tokens: int = 50000):
    node_map = db.get_node_map(doc_id)
    context_parts = []
    total_tokens = 0

    for node_id in node_ids:
        node = node_map[node_id]
        node_tokens = count_tokens(node["text"])

        if total_tokens + node_tokens > max_tokens:
            break  # respect context window limits

        context_parts.append({
            "node_id": node_id,
            "title": node["title"],
            "page_range": f"{node['start_index']}-{node['end_index']}",
            "text": node["text"]
        })
        total_tokens += node_tokens

    return context_parts
```

### Step 5: Answer Generation

Synthesize the final answer with citations:

```python
answer_prompt = f"""
You are a financial analyst assistant. Answer the question using ONLY the
provided context from financial filings. For each claim, cite the source
using [company, year, page range].

If the context is insufficient, clearly state what cannot be determined.

Question: {query}

Context:
{format_context(all_contexts)}

Provide a clear, detailed answer with inline citations.
Also return structured citations in JSON at the end:

```json
{{
    "citations": [
        {{
            "company": "<company>",
            "ticker": "<ticker>",
            "fiscal_year": <year>,
            "node_id": "<node_id>",
            "section_path": "<section title>",
            "page": <start_page>,
            "content_preview": "<first 200 chars of cited text>"
        }}
    ]
}}
```
"""
```

### Step 6: Response Assembly

Build the response object matching the frontend's expected schema:

```python
{
    "answer": "...",
    "retrieval_confidence": {
        "label": "HIGH" | "MEDIUM" | "LOW",
        "answered_by_facts": <count>,        # sub-questions fully answered
        "answered_by_chunks": <count>,       # nodes that contributed
        "unanswered": <count>                # sub-questions not answered
    },
    "resolved_citations": [...],
    "unanswerable_sub_questions": [...],
    "conflicts_detected": [...]
}
```

---

## 3. Confidence Scoring

| Label | Condition |
|---|---|
| HIGH | All sub-questions answered, ≥3 source nodes |
| MEDIUM | Most sub-questions answered (>50%), ≥1 source node |
| LOW | Few sub-questions answered, or zero source nodes |

---

## 4. Multi-Document Aggregation

When a query spans multiple documents (e.g. "Compare AAPL 2022 vs 2023"):

1. Run hybrid tree search independently per document (in parallel)
2. Collect all context parts with metadata labels
3. Pass combined context to the answer LLM with clear document provenance
4. The LLM is prompted to compare/contrast across documents

---

## 5. Token Budget Management

| Component | Budget |
|---|---|
| Tree structure prompt (LLM search) | ~10,000 tokens |
| Retrieved context (answer generation) | ~50,000 tokens |
| Answer generation prompt overhead | ~2,000 tokens |
| Total per query | ~62,000 tokens |

If context from multiple documents exceeds the budget, prioritize nodes
from documents most relevant to the sub-query.

---

## 6. Module Structure

```
backend/
  retrieval/
    __init__.py
    pipeline.py          # orchestrates the full retrieval flow
    query_decomposer.py  # breaks complex queries into sub-queries
    doc_selector.py      # metadata-based document selection
    value_search.py      # embedding-based node scoring
    llm_search.py        # LLM-based tree search
    hybrid_merge.py      # merges results from both search legs
    context_extractor.py # fetches full text for selected nodes
    answer_generator.py  # LLM answer synthesis with citations
    confidence.py        # confidence scoring logic
```
