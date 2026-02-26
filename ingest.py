#!/usr/bin/env python3
"""
CLI ingest script — uploads PDF financial documents to PageIndex and stores metadata locally.

Usage:
    python ingest.py --pdf-dir ./data
    python ingest.py --pdf ./data/AAPL_2023.pdf --company "Apple Inc." --ticker AAPL --fiscal-year 2023
"""

from __future__ import annotations

import argparse
import glob
import logging
import os
import re
import sys
import time

import httpx
from pageindex import PageIndexClient

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import PAGEINDEX_API_KEY, PDF_INPUT_DIR
import metadata_store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("ingest")

CHECKPOINT_FILE = ".ingest_checkpoint"

# ── Checkpoint helpers ───────────────────────────────────────────────────────

def _load_checkpoint(path: str) -> set[str]:
    if not os.path.exists(path):
        return set()
    with open(path) as f:
        return {line.strip() for line in f if line.strip()}


def _save_checkpoint(path: str, doc_key: str) -> None:
    with open(path, "a") as f:
        f.write(doc_key + "\n")


# ── Filename metadata inference ──────────────────────────────────────────────

_FILENAME_PATTERN = re.compile(r"^([A-Z0-9]+)_(\d{4})", re.IGNORECASE)


def _infer_metadata_from_path(path: str) -> dict:
    """Infer ticker and fiscal_year from filename pattern TICKER_YEAR[_anything].pdf."""
    basename = os.path.splitext(os.path.basename(path))[0]
    match = _FILENAME_PATTERN.match(basename)
    if match:
        return {
            "ticker": match.group(1).upper(),
            "fiscal_year": int(match.group(2)),
            "company": match.group(1).upper(),  # placeholder — user can override
        }
    return {}


# ── Service connectivity check ───────────────────────────────────────────────

def _check_services() -> bool:
    """Verify PageIndex API is reachable. Returns True if OK."""
    ok = True

    logger.info("[CHECK] PageIndex API ...")
    if not PAGEINDEX_API_KEY:
        logger.error("[CHECK] PAGEINDEX_API_KEY is not set")
        return False

    try:
        pi = PageIndexClient(api_key=PAGEINDEX_API_KEY)
        result = pi.list_documents(limit=1)
        logger.info(f"[CHECK] PageIndex OK  (total docs: {result.get('total', '?')})")
    except Exception as exc:
        logger.error(f"[CHECK] PageIndex FAIL: {exc}")
        ok = False

    return ok


# ── Ingest one PDF ───────────────────────────────────────────────────────────

def ingest_single_pdf(
    pi_client: PageIndexClient,
    pdf_path: str,
    company: str,
    ticker: str,
    fiscal_year: int,
    doc_type: str = "",
    poll_timeout: int = 300,
) -> dict:
    """Upload a PDF to PageIndex and store metadata locally. Polls until completion."""
    logger.info(f"=== Ingesting: {pdf_path} ===")
    logger.info(f"    Company: {company} | Ticker: {ticker} | FY: {fiscal_year}")

    t0 = time.time()

    # Submit to PageIndex
    logger.info("  [UPLOAD] Submitting to PageIndex...")
    result = pi_client.submit_document(pdf_path)
    doc_id = result["doc_id"]
    logger.info(f"  [UPLOAD] Submitted: doc_id={doc_id}")

    # Store metadata locally
    metadata_store.upsert_document(
        doc_id=doc_id,
        filename=os.path.basename(pdf_path),
        company=company,
        ticker=ticker,
        fiscal_year=fiscal_year,
        doc_type=doc_type,
        status="processing",
    )

    # Poll for completion
    logger.info("  [WAIT] Waiting for processing to complete...")
    deadline = time.time() + poll_timeout
    status = "processing"
    page_count = 0

    while time.time() < deadline:
        time.sleep(5)
        info = pi_client.get_document(doc_id)
        status = info.get("status", "processing")
        page_count = info.get("pageNum", 0)

        if status == "completed":
            metadata_store.update_status(doc_id, "completed", page_count)
            elapsed = time.time() - t0
            logger.info(
                f"  [DONE] Completed in {elapsed:.1f}s — {page_count} pages"
            )
            return {
                "doc_id": doc_id,
                "status": "completed",
                "page_count": page_count,
                "elapsed_seconds": round(elapsed, 1),
            }

        if status == "failed":
            metadata_store.update_status(doc_id, "failed")
            logger.error(f"  [FAIL] PageIndex processing failed for {pdf_path}")
            return {"doc_id": doc_id, "status": "failed", "page_count": 0}

        logger.info(f"  [WAIT] Still processing... ({status})")

    # Timeout
    logger.warning(
        f"  [TIMEOUT] Processing not finished within {poll_timeout}s. "
        f"It will continue server-side. Check status later."
    )
    return {
        "doc_id": doc_id,
        "status": status,
        "page_count": page_count,
        "elapsed_seconds": round(time.time() - t0, 1),
    }


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Ingest PDFs into PageIndex")
    parser.add_argument("--pdf", help="Path to a single PDF file")
    parser.add_argument("--pdf-dir", help="Directory containing PDF files")
    parser.add_argument("--company", default="", help="Company name")
    parser.add_argument("--ticker", default="", help="Ticker symbol")
    parser.add_argument("--fiscal-year", type=int, default=0, help="Fiscal year")
    parser.add_argument("--doc-type", default="", help="Document type hint")
    parser.add_argument(
        "--poll-timeout", type=int, default=300,
        help="Seconds to wait for PageIndex processing (default 300)",
    )
    parser.add_argument(
        "--checkpoint-file", default=CHECKPOINT_FILE,
        help="Checkpoint file path (default: .ingest_checkpoint)",
    )
    parser.add_argument(
        "--reset-checkpoint", action="store_true",
        help="Delete the checkpoint file and start fresh",
    )
    parser.add_argument(
        "--skip-checks", action="store_true",
        help="Skip service connectivity checks",
    )

    args = parser.parse_args()

    # Resolve PDF paths
    pdf_paths: list[str] = []
    if args.pdf:
        pdf_paths.append(os.path.abspath(args.pdf))
    elif args.pdf_dir:
        pdf_dir = os.path.abspath(args.pdf_dir)
        pdf_paths = sorted(glob.glob(os.path.join(pdf_dir, "*.pdf")))
    else:
        pdf_dir = os.path.abspath(PDF_INPUT_DIR)
        pdf_paths = sorted(glob.glob(os.path.join(pdf_dir, "*.pdf")))

    if not pdf_paths:
        logger.error("No PDF files found.")
        sys.exit(1)

    logger.info(f"Found {len(pdf_paths)} PDF(s) to ingest.")

    # Service checks
    if not args.skip_checks:
        if not _check_services():
            logger.error("Service checks failed. Use --skip-checks to bypass.")
            sys.exit(1)

    # Checkpoint
    if args.reset_checkpoint and os.path.exists(args.checkpoint_file):
        os.remove(args.checkpoint_file)
        logger.info(f"Checkpoint file reset: {args.checkpoint_file}")

    completed_ids = _load_checkpoint(args.checkpoint_file)

    # Init PageIndex client
    pi_client = PageIndexClient(api_key=PAGEINDEX_API_KEY)

    results = []
    for pdf_path in pdf_paths:
        basename = os.path.splitext(os.path.basename(pdf_path))[0]

        # Skip if already checkpointed
        if basename in completed_ids:
            logger.info(f"[SKIP] {basename} already ingested (checkpoint). Skipping.")
            continue

        # Resolve metadata
        inferred = _infer_metadata_from_path(pdf_path)
        company = args.company or inferred.get("company", "")
        ticker = args.ticker or inferred.get("ticker", "")
        fiscal_year = args.fiscal_year or inferred.get("fiscal_year", 0)

        try:
            result = ingest_single_pdf(
                pi_client=pi_client,
                pdf_path=pdf_path,
                company=company,
                ticker=ticker,
                fiscal_year=fiscal_year,
                doc_type=args.doc_type,
                poll_timeout=args.poll_timeout,
            )
            results.append(result)

            if result["status"] == "completed":
                _save_checkpoint(args.checkpoint_file, basename)

        except Exception as e:
            logger.error(f"FAILED: {pdf_path}: {e}")
            results.append({"doc_id": "", "status": "error", "error": str(e)})
            continue

    # Summary
    logger.info("=" * 60)
    logger.info("INGEST SUMMARY")
    completed = sum(1 for r in results if r.get("status") == "completed")
    processing = sum(1 for r in results if r.get("status") == "processing")
    failed = sum(1 for r in results if r.get("status") in ("failed", "error"))
    skipped = len(pdf_paths) - len(results)
    logger.info(f"  Completed:  {completed}")
    logger.info(f"  Processing: {processing}")
    logger.info(f"  Failed:     {failed}")
    logger.info(f"  Skipped:    {skipped} (already checkpointed)")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
