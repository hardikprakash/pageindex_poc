"""
Tests for backend.ingest.pipeline — ingest orchestration.

These tests mock the expensive external calls (pageindex tree generation
and Ollama embeddings) so they run fast and deterministically.
"""

import json
import os
import tempfile

import numpy as np
import pytest

from backend.database import init_db, get_db
from backend.ingest.pipeline import (
    ingest_pdf,
    _structure_to_list,
    _remove_fields,
)


# ── helper fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    return db_path


@pytest.fixture
def sample_pdf(tmp_path):
    """Create a minimal valid PDF file."""
    from reportlab.pdfgen import canvas as rl_canvas
    pdf_path = str(tmp_path / "INFY_20F_2022.pdf")
    c = rl_canvas.Canvas(pdf_path)
    c.drawString(100, 750, "This is page 1 of a test document.")
    c.showPage()
    c.drawString(100, 750, "This is page 2 of a test document.")
    c.showPage()
    c.save()
    return pdf_path


MOCK_TREE = [
    {
        "title": "Annual Report 2022",
        "node_id": "0000",
        "start_index": 1,
        "end_index": 2,
        "summary": "Annual report for Infosys 2022.",
        "text": "This is page 1 of a test document. Annual report content here.",
        "nodes": [
            {
                "title": "Financial Statements",
                "node_id": "0001",
                "start_index": 1,
                "end_index": 1,
                "summary": "Financial statements section.",
                "text": "Revenue was $10 billion. Net income was $2 billion.",
            },
            {
                "title": "Risk Factors",
                "node_id": "0002",
                "start_index": 2,
                "end_index": 2,
                "summary": "Risk factors section.",
                "text": "Key risks include currency fluctuation and regulatory changes.",
            },
        ],
    }
]


# ── unit tests for helper functions ──────────────────────────────────────────

class TestStructureToList:
    def test_flat_list(self):
        nodes = _structure_to_list(MOCK_TREE)
        ids = [n["node_id"] for n in nodes]
        assert "0000" in ids
        assert "0001" in ids
        assert "0002" in ids
        assert len(ids) == 3

    def test_single_dict(self):
        node = {"title": "Root", "node_id": "0000", "text": "t"}
        nodes = _structure_to_list(node)
        assert len(nodes) == 1

    def test_nested(self):
        nested = {"title": "A", "node_id": "0000", "nodes": [
            {"title": "B", "node_id": "0001"},
            {"title": "C", "node_id": "0002", "nodes": [
                {"title": "D", "node_id": "0003"},
            ]},
        ]}
        nodes = _structure_to_list(nested)
        assert len(nodes) == 4


class TestRemoveFields:
    def test_removes_text(self):
        data = [{"title": "A", "text": "hello", "nodes": [{"title": "B", "text": "world"}]}]
        result = _remove_fields(data, ["text"])
        assert "text" not in result[0]
        assert "text" not in result[0]["nodes"][0]
        assert result[0]["title"] == "A"

    def test_keeps_other_fields(self):
        data = {"a": 1, "b": 2, "c": 3}
        result = _remove_fields(data, ["b"])
        assert result == {"a": 1, "c": 3}


# ── integration test for full pipeline (mocked externals) ───────────────────

class TestIngestPipeline:
    @pytest.fixture(autouse=True)
    def _patch_externals(self, monkeypatch, sample_pdf):
        """Mock pageindex tree generation and Ollama embeddings."""
        def mock_generate_tree(pdf_path):
            return {
                "doc_name": "INFY_20F_2022",
                "doc_description": "Annual report for Infosys FY2022.",
                "structure": MOCK_TREE,
            }

        async def mock_embed_texts(texts, **kwargs):
            return [np.random.randn(768).astype(np.float32) for _ in texts]

        monkeypatch.setattr("backend.ingest.pipeline._generate_tree", mock_generate_tree)
        monkeypatch.setattr("backend.ingest.pipeline.embed_texts", mock_embed_texts)

    @pytest.mark.asyncio
    async def test_successful_ingest(self, sample_pdf, tmp_db):
        result = await ingest_pdf(
            pdf_path=sample_pdf,
            company="Infosys Ltd",
            db_path=tmp_db,
        )

        assert result.status == "completed"
        assert result.node_count == 3  # 0000, 0001, 0002
        assert result.chunks_created > 0
        assert result.page_count == 2

        # Verify database state
        with get_db(tmp_db) as conn:
            doc = conn.execute("SELECT * FROM documents WHERE id=?", (result.doc_id,)).fetchone()
            assert doc is not None
            assert doc["status"] == "completed"
            assert doc["ticker"] == "INFY"
            assert doc["fiscal_year"] == 2022
            assert doc["doc_type"] == "20-F"

            tree_row = conn.execute("SELECT * FROM trees WHERE doc_id=?", (result.doc_id,)).fetchone()
            assert tree_row is not None
            tree = json.loads(tree_row["tree_json"])
            assert tree[0]["title"] == "Annual Report 2022"

            chunks = conn.execute("SELECT * FROM chunks WHERE doc_id=?", (result.doc_id,)).fetchall()
            assert len(chunks) == result.chunks_created
            # Verify embedding size
            emb = np.frombuffer(chunks[0]["embedding"], dtype=np.float32)
            assert emb.shape == (768,)

    @pytest.mark.asyncio
    async def test_duplicate_detection(self, sample_pdf, tmp_db):
        result1 = await ingest_pdf(pdf_path=sample_pdf, company="Infosys Ltd", db_path=tmp_db)
        assert result1.status == "completed"

        result2 = await ingest_pdf(pdf_path=sample_pdf, company="Infosys Ltd", db_path=tmp_db)
        assert result2.status == "duplicate"

    @pytest.mark.asyncio
    async def test_force_reingest(self, sample_pdf, tmp_db):
        result1 = await ingest_pdf(pdf_path=sample_pdf, company="Infosys Ltd", db_path=tmp_db)
        assert result1.status == "completed"

        result2 = await ingest_pdf(pdf_path=sample_pdf, company="Infosys Ltd", db_path=tmp_db, force=True)
        assert result2.status == "completed"
        assert result2.doc_id != result1.doc_id

        # Old doc should be gone
        with get_db(tmp_db) as conn:
            old = conn.execute("SELECT * FROM documents WHERE id=?", (result1.doc_id,)).fetchone()
            assert old is None

    @pytest.mark.asyncio
    async def test_explicit_metadata_override(self, sample_pdf, tmp_db):
        result = await ingest_pdf(
            pdf_path=sample_pdf,
            company="Infosys Ltd",
            ticker="INFY2",
            fiscal_year=2099,
            doc_type="10-K",
            db_path=tmp_db,
        )
        assert result.status == "completed"

        with get_db(tmp_db) as conn:
            doc = conn.execute("SELECT * FROM documents WHERE id=?", (result.doc_id,)).fetchone()
            assert doc["ticker"] == "INFY2"
            assert doc["fiscal_year"] == 2099
            assert doc["doc_type"] == "10-K"

    @pytest.mark.asyncio
    async def test_bad_filename_no_metadata(self, tmp_path, tmp_db):
        """If filename doesn't match and no explicit metadata → fail."""
        pdf_path = str(tmp_path / "random.pdf")
        # Create a minimal file (doesn't need to be valid PDF for this test)
        with open(pdf_path, "w") as f:
            f.write("not a pdf")

        result = await ingest_pdf(pdf_path=pdf_path, company="Test Co", db_path=tmp_db)
        assert result.status == "failed"
        assert "ticker" in result.message.lower() or "fiscal_year" in result.message.lower()


class TestIngestPipelineNodeMapAndTreeNoText:
    """Verify the derived structures stored in the trees table."""

    @pytest.fixture(autouse=True)
    def _patch(self, monkeypatch, sample_pdf):
        def mock_gen(pdf_path):
            return {"doc_name": "test", "structure": MOCK_TREE}

        async def mock_embed(texts, **kwargs):
            return [np.random.randn(768).astype(np.float32) for _ in texts]

        monkeypatch.setattr("backend.ingest.pipeline._generate_tree", mock_gen)
        monkeypatch.setattr("backend.ingest.pipeline.embed_texts", mock_embed)

    @pytest.mark.asyncio
    async def test_tree_no_text_has_no_text_field(self, sample_pdf, tmp_db):
        result = await ingest_pdf(pdf_path=sample_pdf, company="Test", db_path=tmp_db)
        with get_db(tmp_db) as conn:
            row = conn.execute("SELECT tree_no_text FROM trees WHERE doc_id=?", (result.doc_id,)).fetchone()
        tree_no_text = json.loads(row["tree_no_text"])

        def assert_no_text(node):
            assert "text" not in node, f"Node {node.get('title')} still has 'text'"
            for child in node.get("nodes", []):
                assert_no_text(child)

        for root in tree_no_text:
            assert_no_text(root)

    @pytest.mark.asyncio
    async def test_node_map_has_all_nodes(self, sample_pdf, tmp_db):
        result = await ingest_pdf(pdf_path=sample_pdf, company="Test", db_path=tmp_db)
        with get_db(tmp_db) as conn:
            row = conn.execute("SELECT node_map_json FROM trees WHERE doc_id=?", (result.doc_id,)).fetchone()
        node_map = json.loads(row["node_map_json"])
        assert "0000" in node_map
        assert "0001" in node_map
        assert "0002" in node_map
