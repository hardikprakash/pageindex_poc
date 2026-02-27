"""
Token-aware text chunking for embedding.
"""

import tiktoken

from backend.config import CHUNK_MAX_TOKENS, CHUNK_OVERLAP_TOKENS, CHUNK_MIN_TOKENS

# Use a tokenizer compatible with common models
_encoder = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Return the token count for *text*."""
    if not text:
        return 0
    return len(_encoder.encode(text))


def chunk_text(
    text: str,
    max_tokens: int | None = None,
    overlap: int | None = None,
    min_tokens: int | None = None,
) -> list[dict]:
    """
    Split *text* into overlapping chunks by token count.

    Returns a list of dicts:
        {"content": str, "token_count": int}
    """
    max_tokens = max_tokens if max_tokens is not None else CHUNK_MAX_TOKENS
    overlap = overlap if overlap is not None else CHUNK_OVERLAP_TOKENS
    min_tokens = min_tokens if min_tokens is not None else CHUNK_MIN_TOKENS

    if not text or not text.strip():
        return []

    tokens = _encoder.encode(text)
    total = len(tokens)

    if total <= max_tokens:
        return [{"content": text.strip(), "token_count": total}]

    chunks: list[dict] = []
    start = 0
    while start < total:
        end = min(start + max_tokens, total)
        chunk_tokens = tokens[start:end]
        chunk_text_decoded = _encoder.decode(chunk_tokens)

        if len(chunk_tokens) >= min_tokens:
            chunks.append({
                "content": chunk_text_decoded.strip(),
                "token_count": len(chunk_tokens),
            })

        # Advance the window
        step = max_tokens - overlap
        if step <= 0:
            step = max_tokens  # prevent infinite loop
        start += step

    return chunks
