"""
Tests for backend.ingest.metadata — filename parsing.
"""

import pytest
from backend.ingest.metadata import parse_filename


class TestParseFilename:
    """Verify TICKER_DOCTYPE_YEAR.pdf pattern extraction."""

    def test_standard_20f(self):
        result = parse_filename("INFY_20F_2022.pdf")
        assert result is not None
        assert result.ticker == "INFY"
        assert result.doc_type == "20-F"
        assert result.fiscal_year == 2022

    def test_standard_10k(self):
        result = parse_filename("AAPL_10K_2023.pdf")
        assert result is not None
        assert result.ticker == "AAPL"
        assert result.doc_type == "10-K"
        assert result.fiscal_year == 2023

    def test_lowercase(self):
        result = parse_filename("tsm_20f_2021.pdf")
        assert result is not None
        assert result.ticker == "TSM"
        assert result.doc_type == "20-F"
        assert result.fiscal_year == 2021

    def test_mixed_case(self):
        result = parse_filename("Infy_20f_2020.pdf")
        assert result is not None
        assert result.ticker == "INFY"

    def test_with_directory_prefix(self):
        result = parse_filename("/data/pdfs/INFY_20F_2022.pdf")
        assert result is not None
        assert result.ticker == "INFY"
        assert result.fiscal_year == 2022

    def test_hyphenated_doc_type(self):
        result = parse_filename("TSM_20-F_2023.pdf")
        assert result is not None
        assert result.doc_type == "20-F"

    def test_unknown_doc_type_passthrough(self):
        result = parse_filename("TSM_AnnualReport_2023.pdf")
        assert result is not None
        assert result.doc_type == "AnnualReport"

    def test_no_match_returns_none(self):
        assert parse_filename("random_report.pdf") is None

    def test_no_match_too_few_parts(self):
        assert parse_filename("INFY_2022.pdf") is None

    def test_no_match_wrong_extension(self):
        assert parse_filename("INFY_20F_2022.docx") is None

    def test_empty_string(self):
        assert parse_filename("") is None

    def test_numeric_ticker(self):
        result = parse_filename("600519_20F_2023.pdf")
        assert result is not None
        assert result.ticker == "600519"
