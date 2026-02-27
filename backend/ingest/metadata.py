"""
Filename metadata parser.

Expected format:  <TICKER>_<DOCTYPE>_<YEAR>.pdf
Example:          INFY_20F_2022.pdf
"""

import os
import re
from typing import Optional

from backend.models import ParsedMetadata

# Pattern: TICKER_DOCTYPE_YEAR.pdf  (case-insensitive)
_FILENAME_RE = re.compile(
    r"^(?P<ticker>[A-Za-z0-9]+)_(?P<doc_type>[A-Za-z0-9-]+)_(?P<year>\d{4})\.pdf$",
    re.IGNORECASE,
)

# Map short doc-type tokens to normalised forms
_DOCTYPE_MAP = {
    "20f": "20-F",
    "20-f": "20-F",
    "10k": "10-K",
    "10-k": "10-K",
}


def parse_filename(filename: str) -> Optional[ParsedMetadata]:
    """
    Try to extract metadata from a filename like ``INFY_20F_2022.pdf``.

    Returns ``None`` if the filename doesn't match the expected pattern.
    """
    basename = os.path.basename(filename)
    m = _FILENAME_RE.match(basename)
    if not m:
        return None

    raw_doc_type = m.group("doc_type")
    doc_type = _DOCTYPE_MAP.get(raw_doc_type.lower(), raw_doc_type)

    return ParsedMetadata(
        ticker=m.group("ticker").upper(),
        doc_type=doc_type,
        fiscal_year=int(m.group("year")),
    )
