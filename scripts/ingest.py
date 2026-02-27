#!/usr/bin/env python3
"""
Ingestion CLI — single-document and batch ingestion of PDF financial filings.

Usage
-----
Single document (auto-detect metadata from filename):
    python -m scripts.ingest --pdf data/pdfs/INFY_20F_2022.pdf --company "Infosys Ltd"

Single document (explicit metadata):
    python -m scripts.ingest --pdf data/pdfs/report.pdf \
        --company "Infosys Ltd" --ticker INFY --year 2022 --doc-type 20-F

Batch — ingest every PDF in a directory:
    python -m scripts.ingest --dir data/pdfs/ --company "Infosys Ltd"

Batch with per-company mapping file (JSON):
    python -m scripts.ingest --dir data/pdfs/ --company-map data/company_map.json

The company map JSON looks like:
    {
        "INFY": "Infosys Ltd",
        "TSM": "Taiwan Semiconductor Mfg Co Ltd"
    }

Force re-ingest (overwrite existing):
    python -m scripts.ingest --pdf data/pdfs/INFY_20F_2022.pdf \
        --company "Infosys Ltd" --force
"""

import argparse
import asyncio
import glob
import json
import logging
import os
import sys
import time

# Ensure repo root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.ingest.pipeline import ingest_pdf  # noqa: E402
from backend.ingest.embedder import check_ollama  # noqa: E402
from backend.database import init_db             # noqa: E402
from backend import config                       # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ingest")


def _resolve_company(filename: str, company: str | None, company_map: dict | None) -> str | None:
    """
    Determine the company name:
      1. Explicit --company flag
      2. Ticker lookup in company_map
      3. None (will trigger an error)
    """
    if company:
        return company
    if company_map:
        from backend.ingest.metadata import parse_filename
        parsed = parse_filename(filename)
        if parsed and parsed.ticker in company_map:
            return company_map[parsed.ticker]
    return None


async def _ingest_one(
    pdf_path: str,
    company: str | None,
    ticker: str | None,
    fiscal_year: int | None,
    doc_type: str | None,
    force: bool,
    company_map: dict | None,
) -> bool:
    """Ingest a single PDF. Returns True on success."""
    basename = os.path.basename(pdf_path)
    resolved_company = _resolve_company(basename, company, company_map)

    if not resolved_company:
        logger.error("No company name for %s — use --company or --company-map", basename)
        return False

    t0 = time.time()
    logger.info("▶ Ingesting %s", basename)

    result = await ingest_pdf(
        pdf_path=pdf_path,
        company=resolved_company,
        ticker=ticker,
        fiscal_year=fiscal_year,
        doc_type=doc_type,
        force=force,
    )

    elapsed = time.time() - t0

    if result.status == "completed":
        logger.info(
            "✓ %s → %s  |  %d nodes, %d chunks, %d pages  [%.1fs]",
            basename, result.doc_id, result.node_count,
            result.chunks_created, result.page_count, elapsed,
        )
        return True
    elif result.status == "duplicate":
        logger.warning("⊘ %s — %s", basename, result.message)
        return True  # not a failure
    else:
        logger.error("✗ %s — %s", basename, result.message)
        return False


async def _preflight_checks() -> bool:
    """
    Verify that all required services are reachable before starting ingestion.
    Returns True if all checks pass, False otherwise.
    """
    ok = True

    # ── 1. OpenRouter API key ────────────────────────────────────────────────
    if not config.OPENAI_API_KEY:
        logger.error(
            "✗ OPENAI_API_KEY is not set. "
            "Add it to your .env file (format: sk-or-v1-...)."
        )
        ok = False
    else:
        logger.info("✓ OpenRouter API key found")

    # ── 2. Ollama embedding service ──────────────────────────────────────────
    ollama_ok = await check_ollama()
    if not ollama_ok:
        logger.error(
            "✗ Ollama is not reachable at %s or model '%s' is not loaded. "
            "Run: docker compose up -d",
            config.OLLAMA_URL,
            config.EMBEDDING_MODEL,
        )
        ok = False
    else:
        logger.info(
            "✓ Ollama reachable at %s (model: %s)",
            config.OLLAMA_URL,
            config.EMBEDDING_MODEL,
        )

    return ok


async def run(args: argparse.Namespace):
    if not await _preflight_checks():
        logger.error("Pre-flight checks failed — aborting.")
        sys.exit(1)

    init_db()

    company_map: dict | None = None
    if args.company_map:
        with open(args.company_map) as f:
            company_map = json.load(f)
        logger.info("Loaded company map with %d entries", len(company_map))

    pdf_paths: list[str] = []

    if args.pdf:
        pdf_paths.append(args.pdf)
    elif args.dir:
        pattern = os.path.join(args.dir, "*.pdf")
        pdf_paths = sorted(glob.glob(pattern))
        if not pdf_paths:
            logger.error("No PDF files found in %s", args.dir)
            sys.exit(1)
        logger.info("Found %d PDFs in %s", len(pdf_paths), args.dir)

    successes = 0
    failures = 0

    for path in pdf_paths:
        ok = await _ingest_one(
            pdf_path=path,
            company=args.company,
            ticker=args.ticker,
            fiscal_year=args.year,
            doc_type=args.doc_type,
            force=args.force,
            company_map=company_map,
        )
        if ok:
            successes += 1
        else:
            failures += 1

    logger.info("━" * 60)
    logger.info("Done: %d succeeded, %d failed, %d total", successes, failures, len(pdf_paths))

    if failures:
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Ingest PDF financial filings into the PageIndex corpus.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--pdf", type=str, help="Path to a single PDF file")
    source.add_argument("--dir", type=str, help="Directory containing PDFs for batch ingest")

    parser.add_argument("--company", type=str, help="Company name (required for single, or use --company-map)")
    parser.add_argument("--ticker", type=str, help="Override ticker (auto-detected from filename)")
    parser.add_argument("--year", type=int, help="Override fiscal year (auto-detected from filename)")
    parser.add_argument("--doc-type", type=str, help="Override doc type (auto-detected from filename)")
    parser.add_argument("--company-map", type=str, help="Path to JSON mapping ticker → company name")
    parser.add_argument("--force", action="store_true", help="Overwrite existing documents")

    args = parser.parse_args()

    if not args.company and not args.company_map:
        # For batch mode, company_map is expected; for single mode, company is required
        if args.pdf:
            parser.error("--company is required when ingesting a single PDF (or use --company-map)")

    asyncio.run(run(args))


if __name__ == "__main__":
    main()
