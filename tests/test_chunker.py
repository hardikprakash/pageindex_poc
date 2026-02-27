"""
Tests for backend.ingest.chunker — text chunking.
"""

import pytest
from backend.ingest.chunker import chunk_text, count_tokens


class TestCountTokens:
    def test_empty_string(self):
        assert count_tokens("") == 0

    def test_none_string(self):
        assert count_tokens(None) == 0

    def test_short_text(self):
        n = count_tokens("Hello world")
        assert n > 0 and n < 10

    def test_longer_text(self):
        text = "The quick brown fox jumps over the lazy dog. " * 50
        n = count_tokens(text)
        assert n > 100


class TestChunkText:
    def test_empty_returns_empty(self):
        assert chunk_text("") == []

    def test_whitespace_only_returns_empty(self):
        assert chunk_text("   \n\n  ") == []

    def test_short_text_single_chunk(self):
        text = "Hello world, this is a test."
        chunks = chunk_text(text, max_tokens=512)
        assert len(chunks) == 1
        assert chunks[0]["content"] == text.strip()
        assert chunks[0]["token_count"] > 0

    def test_long_text_splits(self):
        # Build text that's guaranteed to be > 512 tokens
        text = "The quick brown fox jumps over the lazy dog. " * 200
        chunks = chunk_text(text, max_tokens=100, overlap=10, min_tokens=5)
        assert len(chunks) > 1
        # Each chunk should respect the token limit
        for c in chunks:
            assert c["token_count"] <= 100

    def test_overlap_creates_more_chunks(self):
        text = "word " * 500  # ~500 tokens
        no_overlap = chunk_text(text, max_tokens=100, overlap=0, min_tokens=1)
        with_overlap = chunk_text(text, max_tokens=100, overlap=50, min_tokens=1)
        assert len(with_overlap) > len(no_overlap)

    def test_min_tokens_filter(self):
        # Create text that would produce a tiny trailing chunk
        text = "word " * 105  # ~105 tokens → 100 + 5
        chunks = chunk_text(text, max_tokens=100, overlap=0, min_tokens=10)
        # The trailing 5-token chunk should be filtered out
        for c in chunks:
            assert c["token_count"] >= 10

    def test_chunk_content_is_stripped(self):
        text = "  hello world this is a test  "
        chunks = chunk_text(text, max_tokens=512)
        assert chunks[0]["content"] == text.strip()

    def test_default_params(self):
        # Just make sure defaults don't crash
        text = "Reasonable length text for default params. " * 10
        chunks = chunk_text(text)
        assert len(chunks) >= 1
