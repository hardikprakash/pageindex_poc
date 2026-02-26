"""
API request / response models for FastAPI.
"""

from pydantic import BaseModel, Field
from typing import Optional


class QueryRequest(BaseModel):
    query: str
    companies: list[str] = Field(default_factory=list)
    years: list[int] = Field(default_factory=list)


class QueryResponse(BaseModel):
    answer: str
    query: str = ""
    doc_ids_used: list[str] = Field(default_factory=list)
    citations: list[dict] = Field(default_factory=list)
    usage: dict = Field(default_factory=dict)


class IngestResponse(BaseModel):
    doc_id: str
    filename: str
    status: str
    page_count: int = 0


class DocumentInfo(BaseModel):
    doc_id: str
    filename: str = ""
    company: str = ""
    ticker: str = ""
    fiscal_year: int = 0
    doc_type: str = ""
    page_count: int = 0
    status: str = "processing"
    created_at: str = ""


class CorpusResponse(BaseModel):
    documents: list[DocumentInfo] = Field(default_factory=list)
