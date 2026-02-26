"""
Centralized configuration.  All env vars read from here.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── PageIndex ────────────────────────────────────────────────────────────────
PAGEINDEX_API_KEY = os.environ.get("PAGEINDEX_API_KEY", "")

# ── Optional LLM via OpenRouter (for sub-question decomposition) ─────────────
OPENROUTER_API_KEY = os.environ.get(
    "OPENROUTER_API_KEY", os.environ.get("OPENAI_API_KEY", "")
)
OPENROUTER_BASE_URL = os.environ.get(
    "OPENROUTER_BASE_URL",
    os.environ.get("OPENAI_API_BASE_URL", "https://openrouter.ai/api/v1"),
)
LLM_MODEL = os.environ.get(
    "LLM_MODEL", os.environ.get("MODEL_NAME", "openai/gpt-4o-2024-11-20")
)

# ── Paths ────────────────────────────────────────────────────────────────────
PDF_INPUT_DIR = os.environ.get("PDF_INPUT_DIR", "./data")
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")

# ── Metadata DB ──────────────────────────────────────────────────────────────
METADATA_DB_PATH = os.environ.get("METADATA_DB_PATH", "metadata.db")
