"""
Tests for the FastAPI endpoints.
Uses TestClient; PageIndex calls are not mocked — these test request/response shapes.
"""

import os
import sys
import tempfile
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Override DB before imports
_TMP_DB = tempfile.mktemp(suffix=".db")
os.environ["METADATA_DB_PATH"] = _TMP_DB
os.environ["PAGEINDEX_API_KEY"] = "test-fake-key"

from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client with mocked PageIndex client."""
    # Patch PageIndexClient before importing the app
    with patch("api.main.PageIndexClient") as MockPI:
        mock_pi = MagicMock()
        MockPI.return_value = mock_pi

        # Mock list_documents for health check
        mock_pi.list_documents.return_value = {"total": 0, "documents": []}

        from api.main import app
        with TestClient(app) as tc:
            # Store mock for assertions
            tc._mock_pi = mock_pi
            yield tc

    # Cleanup
    if os.path.exists(_TMP_DB):
        os.remove(_TMP_DB)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_corpus_empty(client):
    resp = client.get("/corpus")
    assert resp.status_code == 200
    data = resp.json()
    assert data["documents"] == []


def test_query_no_docs(client):
    resp = client.post("/query", json={"query": "test question"})
    assert resp.status_code == 422  # No documents match
