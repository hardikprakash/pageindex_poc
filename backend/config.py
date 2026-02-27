"""
Central configuration — reads environment variables and provides defaults.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── LLM (OpenRouter) ─────────────────────────────────────────────────────────
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY") or os.getenv("CHATGPT_API_KEY", "")
OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
LLM_MODEL: str = os.getenv("LLM_MODEL", "openai/gpt-5.2")

# ── Ollama (embeddings) ──────────────────────────────────────────────────────
OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11435")
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "nomic-embed-text-v2-moe")
EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", "768"))

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "data/pageindex.db")

# ── Uploads ───────────────────────────────────────────────────────────────────
UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "data/uploads")

# ── PageIndex tree generation defaults ────────────────────────────────────────
PAGEINDEX_MODEL: str = os.getenv("PAGEINDEX_MODEL", LLM_MODEL)
TOC_CHECK_PAGES: int = int(os.getenv("TOC_CHECK_PAGES", "20"))
MAX_PAGES_PER_NODE: int = int(os.getenv("MAX_PAGES_PER_NODE", "10"))
MAX_TOKENS_PER_NODE: int = int(os.getenv("MAX_TOKENS_PER_NODE", "20000"))

# ── Chunking ──────────────────────────────────────────────────────────────────
CHUNK_MAX_TOKENS: int = int(os.getenv("CHUNK_MAX_TOKENS", "512"))
CHUNK_OVERLAP_TOKENS: int = int(os.getenv("CHUNK_OVERLAP_TOKENS", "64"))
CHUNK_MIN_TOKENS: int = int(os.getenv("CHUNK_MIN_TOKENS", "32"))

# ── Embedding batch size ──────────────────────────────────────────────────────
EMBED_BATCH_SIZE: int = int(os.getenv("EMBED_BATCH_SIZE", "32"))
