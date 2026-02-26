"""
Streamlit frontend — thin client for the Financial Filings PageIndex Agent.
Communicates with the FastAPI backend via HTTP.

Entry point: streamlit run frontend/app.py
"""

import streamlit as st
import httpx
import os
from datetime import datetime
from collections import defaultdict

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Financial Filings Agent (PageIndex)",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Session State ────────────────────────────────────────────────────────────
if "query_history" not in st.session_state:
    st.session_state.query_history = []
if "messages" not in st.session_state:
    st.session_state.messages = []


# ── Helpers ──────────────────────────────────────────────────────────────────

def fetch_corpus() -> list[dict]:
    """Fetch corpus info from backend."""
    try:
        response = httpx.get(f"{BACKEND_URL}/corpus", timeout=10.0)
        if response.status_code == 200:
            return response.json().get("documents", [])
    except Exception:
        pass
    return []


# ── Page 1: Query ────────────────────────────────────────────────────────────

def render_query_page():
    st.title("📊 Financial Filings Agent")
    st.caption("Ask questions about financial filings — powered by PageIndex reasoning-based RAG.")

    # Sidebar
    corpus = fetch_corpus()
    available_companies = sorted(set(d.get("company", "") for d in corpus if d.get("company")))
    available_years = sorted(set(d.get("fiscal_year", 0) for d in corpus if d.get("fiscal_year")))

    with st.sidebar:
        st.markdown("### Filters")

        selected_companies = st.multiselect(
            "Filter by company",
            options=available_companies,
            default=available_companies,
        )

        selected_years = st.multiselect(
            "Filter by fiscal year",
            options=available_years,
            default=available_years,
        )

        st.markdown("---")
        st.markdown("**About**")
        st.caption(
            "PageIndex reasoning-based RAG agent for financial document Q&A. "
            "Uses tree-structured document indexing with agentic retrieval "
            "for accurate, cited answers. No vector DB or chunking required."
        )

        # Recent queries
        if st.session_state.query_history:
            st.markdown("---")
            st.markdown("**Recent queries**")
            for item in reversed(st.session_state.query_history[-5:]):
                if st.button(item["query"][:60] + "...", key=f"hist_{item['timestamp']}"):
                    st.session_state["rerun_query"] = item["query"]

    # Main area
    rerun_query = st.session_state.pop("rerun_query", None)
    query = st.text_area(
        "Ask a question about the financial filings",
        value=rerun_query or "",
        placeholder="e.g. How did Company A's gross margin trend from 2020 to 2023?",
        height=100,
    )

    col1, col2 = st.columns([1, 5])
    with col1:
        submit = st.button("Ask", type="primary")
    with col2:
        st.caption(f"{len(query)} characters")

    if submit and query.strip():
        with st.spinner("Querying PageIndex (reasoning-based retrieval)..."):
            try:
                response = httpx.post(
                    f"{BACKEND_URL}/query",
                    json={
                        "query": query,
                        "companies": selected_companies,
                        "years": selected_years,
                    },
                    timeout=120.0,
                )
            except httpx.ConnectError:
                st.error("Cannot connect to backend. Is the FastAPI server running?")
                return
            except Exception as e:
                st.error(f"Request failed: {e}")
                return

        if response.status_code == 200:
            data = response.json()
            render_answer(data)

            # Save to history
            st.session_state.query_history.append({
                "query": query,
                "response": data,
                "timestamp": datetime.now().isoformat(),
            })

        elif response.status_code == 422:
            st.error(f"Query error: {response.json().get('detail', 'Unknown error')}")
        else:
            st.error(f"Backend error: {response.status_code}")


def render_answer(data: dict):
    """Render the PageIndex agent's response."""
    # 1. Answer text
    st.markdown("---")
    st.markdown(data.get("answer", "No answer generated."))

    # 2. Citations
    citations = data.get("citations", [])
    if citations:
        st.markdown("---")
        st.markdown(f"**Sources cited ({len(citations)}):**")
        for c in citations:
            st.markdown(f"- 📄 **{c.get('document', '')}** · page {c.get('page', '')}")

    # 3. Usage stats
    usage = data.get("usage", {})
    if usage:
        with st.expander("Token usage"):
            cols = st.columns(3)
            cols[0].metric("Prompt tokens", usage.get("prompt_tokens", 0))
            cols[1].metric("Completion tokens", usage.get("completion_tokens", 0))
            cols[2].metric("Total tokens", usage.get("total_tokens", 0))

    # 4. Doc IDs used
    doc_ids = data.get("doc_ids_used", [])
    if doc_ids:
        with st.expander(f"Documents queried ({len(doc_ids)})"):
            for did in doc_ids:
                st.code(did)

    # 5. Debug: full response
    with st.expander("Debug: full response"):
        st.json(data)


# ── Page 2: Corpus ───────────────────────────────────────────────────────────

def render_corpus_page():
    st.title("📁 Corpus Management")

    tab1, tab2 = st.tabs(["Ingested Documents", "Ingest New"])

    with tab1:
        render_corpus_tab()

    with tab2:
        render_ingest_tab()


def render_corpus_tab():
    """Show all ingested documents."""
    try:
        response = httpx.get(f"{BACKEND_URL}/corpus", timeout=10.0)
        docs = response.json().get("documents", [])
    except Exception:
        st.error("Cannot connect to backend.")
        return

    if not docs:
        st.info("No documents ingested yet. Go to 'Ingest New' to add documents.")
        return

    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Documents", len(docs))
    col2.metric("Companies", len(set(d.get("company", "") for d in docs)))
    col3.metric("Years covered", len(set(d.get("fiscal_year", 0) for d in docs)))
    col4.metric(
        "Total pages",
        sum(d.get("page_count", 0) for d in docs),
    )

    # Documents table
    import pandas as pd

    df = pd.DataFrame(docs)
    display_cols = [
        c for c in [
            "company", "ticker", "fiscal_year", "doc_type",
            "page_count", "status", "doc_id", "created_at",
        ]
        if c in df.columns
    ]
    if display_cols:
        df = df[display_cols].sort_values(["company", "fiscal_year"])
        st.dataframe(df, use_container_width=True, hide_index=True)

    # Delete button
    st.markdown("---")
    st.markdown("**Delete a document**")
    doc_ids = [d.get("doc_id", "") for d in docs]
    doc_labels = [
        f"{d.get('company', '')} — FY{d.get('fiscal_year', '')} ({d.get('doc_id', '')})"
        for d in docs
    ]
    selected_idx = st.selectbox("Select document to delete", range(len(doc_labels)), format_func=lambda i: doc_labels[i])
    if st.button("Delete", type="secondary"):
        doc_id = doc_ids[selected_idx]
        try:
            resp = httpx.delete(f"{BACKEND_URL}/corpus/{doc_id}", timeout=10.0)
            if resp.status_code == 200:
                st.success(f"Deleted {doc_id}")
                st.rerun()
            else:
                st.error(f"Delete failed: {resp.text}")
        except Exception as e:
            st.error(f"Error: {e}")


def render_ingest_tab():
    """Upload and ingest new PDFs."""
    st.markdown(
        "Upload one or more PDF financial filings. They will be processed by "
        "PageIndex — tree generation + OCR happens automatically."
    )

    col1, col2 = st.columns(2)
    with col1:
        company_name = st.text_input("Company name", placeholder="Apple Inc.")
        ticker = st.text_input("Ticker / short ID", placeholder="AAPL")
    with col2:
        fiscal_year = st.number_input(
            "Fiscal year", min_value=2000, max_value=2030, value=2023
        )
        doc_type_hint = st.selectbox(
            "Document type hint (optional)",
            options=["", "20-F", "10-K", "annual_report", "earnings_release", "other"],
        )

    uploaded_files = st.file_uploader(
        "Upload PDF(s)",
        type=["pdf"],
        accept_multiple_files=True,
    )

    if st.button("Start Ingest", type="primary", disabled=not uploaded_files or not company_name):
        progress = st.progress(0, text="Starting ingest...")
        status_text = st.empty()

        for i, file in enumerate(uploaded_files):
            status_text.text(f"Uploading {file.name} to PageIndex...")
            try:
                response = httpx.post(
                    f"{BACKEND_URL}/ingest",
                    files={"file": (file.name, file.getvalue(), "application/pdf")},
                    data={
                        "company": company_name,
                        "ticker": ticker,
                        "fiscal_year": str(fiscal_year),
                        "doc_type_hint": doc_type_hint,
                    },
                    timeout=300.0,
                )
                progress.progress((i + 1) / len(uploaded_files))

                if response.status_code == 200:
                    result = response.json()
                    status = result.get("status", "unknown")
                    pages = result.get("page_count", 0)
                    doc_id = result.get("doc_id", "")
                    if status == "completed":
                        st.success(
                            f"✅ {file.name}: Processed ({pages} pages) — {doc_id}"
                        )
                    else:
                        st.info(
                            f"⏳ {file.name}: Still processing on PageIndex — {doc_id}. "
                            "Refresh corpus page to check status."
                        )
                else:
                    st.error(f"{file.name}: ingest failed — {response.text}")
            except Exception as e:
                st.error(f"{file.name}: error — {e}")

        progress.progress(1.0, text="Ingest complete.")
        st.balloons()


# ── Page Routing ─────────────────────────────────────────────────────────────
page = st.sidebar.radio("Navigation", ["Query", "Corpus"], label_visibility="collapsed")

if page == "Query":
    render_query_page()
elif page == "Corpus":
    render_corpus_page()
