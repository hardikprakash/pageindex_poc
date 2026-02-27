"""
Pydantic models shared across the backend.
"""

from typing import Optional
from pydantic import BaseModel


class DocumentRecord(BaseModel):
    id: str
    company: str
    ticker: str
    fiscal_year: int
    doc_type: str
    filename: str
    page_count: Optional[int] = None
    total_tokens: Optional[int] = None
    node_count: int = 0
    chunk_count: int = 0
    status: str = "processing"
    error_message: Optional[str] = None
    ingest_timestamp: str = ""


class IngestResult(BaseModel):
    doc_id: str
    status: str
    chunks_created: int = 0
    facts_created: int = 0
    entities_created: int = 0
    node_count: int = 0
    page_count: int = 0
    message: str = ""


class ParsedMetadata(BaseModel):
    ticker: str
    doc_type: str
    fiscal_year: int
