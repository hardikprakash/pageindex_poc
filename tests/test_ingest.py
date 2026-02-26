"""
Tests for the CLI ingest script helpers.
"""

import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ingest import _infer_metadata_from_path, _load_checkpoint, _save_checkpoint


def test_infer_metadata_standard():
    meta = _infer_metadata_from_path("/data/AAPL_2023.pdf")
    assert meta["ticker"] == "AAPL"
    assert meta["fiscal_year"] == 2023


def test_infer_metadata_with_suffix():
    meta = _infer_metadata_from_path("/data/INFY_2024_20F.pdf")
    assert meta["ticker"] == "INFY"
    assert meta["fiscal_year"] == 2024


def test_infer_metadata_no_match():
    meta = _infer_metadata_from_path("/data/random_report.pdf")
    assert meta == {}


def test_checkpoint_roundtrip():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        path = f.name

    try:
        # Fresh file → empty set
        os.remove(path)
        assert _load_checkpoint(path) == set()

        # Save a few
        _save_checkpoint(path, "AAPL_2023")
        _save_checkpoint(path, "INFY_2024")

        loaded = _load_checkpoint(path)
        assert loaded == {"AAPL_2023", "INFY_2024"}
    finally:
        if os.path.exists(path):
            os.remove(path)
