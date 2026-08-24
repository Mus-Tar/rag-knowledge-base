from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ParsedChunk:
    page: int
    chunk_index: int
    content: str


@dataclass(frozen=True)
class DocumentSummary:
    id: str
    original_filename: str
    sha256: str
    page_count: int
    chunk_count: int
    status: str
    created_at: datetime
    failure_reason: str | None = None
    index_version: str | None = None
    processing_started_at: datetime | None = None
    processed_at: datetime | None = None


@dataclass(frozen=True)
class VectorChunk:
    id: str
    document_id: str
    page: int
    chunk_index: int
    content: str


@dataclass(frozen=True)
class Citation:
    document_id: str
    filename: str
    page: int
    chunk_id: str
    excerpt: str


@dataclass(frozen=True)
class RetrievalMetadata:
    query: str
    candidate_count: int
    result_count: int
    retrieval_ms: float
    rerank_ms: float
    index_version: str


@dataclass(frozen=True)
class ConversationSummary:
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class MessageSummary:
    id: str
    conversation_id: str
    role: str
    content: str
    citations: list[Citation]
    created_at: datetime
