"""
Pydantic models for Levitech MVP.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class CaseMetadata(BaseModel):
    """Editable case information."""
    case_id: str
    client_name: str = ""
    matter_type: str = ""  # e.g., "immigration", "employment"
    key_dates: list[str] = Field(default_factory=list)
    jurisdiction: str = "UK"
    notes: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ChunkProvenance(BaseModel):
    """Tracks the source of a document chunk."""
    chunk_id: str
    file_name: str
    page_num: Optional[int] = None  # For PDFs
    para_idx: Optional[int] = None  # For Word docs
    char_start: int = 0
    char_end: int = 0
    ocr: bool = False  # True if text was extracted via OCR


class DocumentChunk(BaseModel):
    """A chunk of text from a client document with provenance."""
    text: str
    provenance: ChunkProvenance
    embedding: Optional[list[float]] = None


class LegalSource(BaseModel):
    """A fetched legal source with snapshot data."""
    id: str  # Unique identifier (hash of URL)
    url: str
    domain: str
    title: str = ""
    excerpt: str = ""  # Short excerpt for display
    text: str = ""  # Full extracted text
    html: str = ""  # Raw HTML (for debugging)
    content_hash: str = ""  # SHA-256 of text content
    fetched_at: datetime = Field(default_factory=datetime.utcnow)


class Citation(BaseModel):
    """A citation extracted from LLM response."""
    id: str  # Reference to LegalSource.id or chunk_id
    source_type: str  # "legal" or "client"
    url: Optional[str] = None  # For legal sources
    domain: Optional[str] = None  # For legal sources
    file_name: Optional[str] = None  # For client docs
    page_num: Optional[int] = None  # For client docs
    excerpt: str  # The quoted text


class RollingSummary(BaseModel):
    """Generated case summary that persists across turns."""
    version: int = 1
    client_background: str = ""
    key_chronology: list[str] = Field(default_factory=list)
    legal_issues_identified: list[str] = Field(default_factory=list)
    source_references: list[str] = Field(default_factory=list)  # e.g., "Doc A p2"
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class SessionState(BaseModel):
    """Persisted session state for a case (not reliant on chat history)."""
    case_id: str
    retrieved_facts: list[str] = Field(default_factory=list)  # Last N retrieved chunks
    legal_sources_used: list[str] = Field(default_factory=list)  # Source IDs
    rolling_summary: RollingSummary = Field(default_factory=RollingSummary)
    turn_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class SearchResult(BaseModel):
    """A search result from hybrid search."""
    chunk_id: str
    text: str
    score: float
    provenance: ChunkProvenance
    source_type: str = "client"  # "client" or "legal"


class EvidenceItem(BaseModel):
    """Evidence item in answer response."""
    source_type: str  # "client" or "legal"
    file_name: Optional[str] = None
    page_num: Optional[int] = None
    url: Optional[str] = None
    domain: Optional[str] = None
    excerpt: str


class ChatRequest(BaseModel):
    """Request body for chat endpoint."""
    question: str


class ChatResponse(BaseModel):
    """Response from chat endpoint."""
    answer: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    legal_sources: list[LegalSource] = Field(default_factory=list)
    session_updated: bool = False


class AnswerResponse(BaseModel):
    """Internal response from answer engine."""
    answer: str
    client_evidence: list[SearchResult] = Field(default_factory=list)
    legal_sources: list[LegalSource] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    citations_valid: bool = True
    validation_errors: list[str] = Field(default_factory=list)


class CaseCreateRequest(BaseModel):
    """Request to create a new case."""
    case_id: str
    client_name: str = ""
    matter_type: str = ""


class DocumentInfo(BaseModel):
    """Information about an uploaded document."""
    file_name: str
    file_size: int
    chunk_count: int
    ocr_applied: bool = False
    indexed_at: datetime = Field(default_factory=datetime.utcnow)
