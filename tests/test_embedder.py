"""
Tests for backend.ingest.embedder — Ollama embedding client.

These test the logic with a mocked HTTP server, not actual Ollama.
"""

import numpy as np
import pytest
import httpx

from backend.ingest.embedder import embed_texts, _embed_batch


class TestEmbedBatch:
    @pytest.mark.asyncio
    async def test_returns_numpy_arrays(self, monkeypatch):
        """Verify that _embed_batch returns numpy float32 arrays."""
        async def mock_post(self, url, **kwargs):
            texts = kwargs.get("json", {}).get("input", [])
            embeddings = [[0.1] * 768 for _ in texts]
            request = httpx.Request("POST", url)
            resp = httpx.Response(200, json={"embeddings": embeddings}, request=request)
            return resp

        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

        async with httpx.AsyncClient() as client:
            result = await _embed_batch(client, ["hello", "world"], "test-model", max_retries=1)

        assert len(result) == 2
        assert all(isinstance(e, np.ndarray) for e in result)
        assert all(e.dtype == np.float32 for e in result)
        assert all(e.shape == (768,) for e in result)


class TestEmbedTexts:
    @pytest.mark.asyncio
    async def test_batching(self, monkeypatch):
        """Verify texts are split into batches."""
        call_count = 0

        async def mock_post(self, url, **kwargs):
            nonlocal call_count
            call_count += 1
            texts = kwargs.get("json", {}).get("input", [])
            embeddings = [[0.5] * 768 for _ in texts]
            request = httpx.Request("POST", url)
            return httpx.Response(200, json={"embeddings": embeddings}, request=request)

        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

        texts = [f"text_{i}" for i in range(50)]
        result = await embed_texts(texts, batch_size=20)

        assert len(result) == 50
        assert call_count == 3  # 20 + 20 + 10

    @pytest.mark.asyncio
    async def test_empty_input(self, monkeypatch):
        async def mock_post(self, url, **kwargs):
            request = httpx.Request("POST", url)
            return httpx.Response(200, json={"embeddings": []}, request=request)

        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

        result = await embed_texts([])
        assert result == []
