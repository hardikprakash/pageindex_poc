"""
Ollama embedding client — generates 768-d vectors via the local Ollama container.
"""

import logging
from typing import Sequence

import httpx
import numpy as np

from backend.config import OLLAMA_URL, EMBEDDING_MODEL, EMBEDDING_DIM, EMBED_BATCH_SIZE

logger = logging.getLogger(__name__)


async def embed_texts(
    texts: Sequence[str],
    model: str | None = None,
    batch_size: int | None = None,
    max_retries: int = 3,
) -> list[np.ndarray]:
    """
    Embed a list of texts via Ollama.

    Returns a list of float32 numpy arrays, each of shape (EMBEDDING_DIM,).
    Texts are processed in batches to avoid overloading Ollama.
    """
    model = model or EMBEDDING_MODEL
    batch_size = batch_size or EMBED_BATCH_SIZE
    all_embeddings: list[np.ndarray] = []

    async with httpx.AsyncClient(timeout=120.0) as client:
        for start in range(0, len(texts), batch_size):
            batch = list(texts[start : start + batch_size])
            embedding_batch = await _embed_batch(client, batch, model, max_retries)
            all_embeddings.extend(embedding_batch)

    return all_embeddings


async def _embed_batch(
    client: httpx.AsyncClient,
    texts: list[str],
    model: str,
    max_retries: int,
) -> list[np.ndarray]:
    """Embed a single batch with retries."""
    for attempt in range(max_retries):
        try:
            resp = await client.post(
                f"{OLLAMA_URL}/api/embed",
                json={"model": model, "input": texts},
            )
            resp.raise_for_status()
            data = resp.json()
            embeddings = data.get("embeddings", [])
            return [np.array(e, dtype=np.float32) for e in embeddings]
        except Exception as e:
            logger.warning("Embedding batch attempt %d failed: %s", attempt + 1, e)
            if attempt < max_retries - 1:
                import asyncio
                await asyncio.sleep(2 ** attempt)
            else:
                raise
    return []  # unreachable


async def check_ollama() -> bool:
    """Return True if Ollama is reachable and the embedding model is available."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{OLLAMA_URL}/api/tags")
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
            # Model names may include tag, e.g. "nomic-embed-text-v2-moe:latest"
            return any(EMBEDDING_MODEL in m for m in models)
    except Exception:
        return False
