from time import perf_counter
from typing import Any

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict, Field

from rag_api.domain.models import RetrievalMetadata, VectorChunk


class ChromaRetriever(BaseRetriever):
    vector_store: Any = Field(exclude=True)
    reranker: Any = Field(exclude=True)
    limit: int = 4
    candidate_limit: int = 12
    model_config = ConfigDict(arbitrary_types_allowed=True)

    def retrieve(self, query: str) -> tuple[list[Document], RetrievalMetadata]:
        started_at = perf_counter()
        vector_chunks = self.vector_store.search(query, self.candidate_limit)
        lexical_chunks = self.vector_store.lexical_search(query, self.candidate_limit)
        candidates = _unique_chunks(vector_chunks + lexical_chunks)
        retrieval_ms = round((perf_counter() - started_at) * 1000, 2)
        rerank_started_at = perf_counter()
        chunks = self.reranker.rank(query, candidates, self.limit)
        rerank_ms = round((perf_counter() - rerank_started_at) * 1000, 2)
        return (
            [_to_document(chunk) for chunk in chunks],
            RetrievalMetadata(
                query=query,
                candidate_count=len(candidates),
                result_count=len(chunks),
                retrieval_ms=retrieval_ms,
                rerank_ms=rerank_ms,
                index_version=self.vector_store.index_version,
            ),
        )

    def _get_relevant_documents(self, query: str, *, run_manager: Any) -> list[Document]:
        documents, _ = self.retrieve(query)
        return documents


def _unique_chunks(chunks: list[VectorChunk]) -> list[VectorChunk]:
    return list({chunk.id: chunk for chunk in chunks}.values())


def _to_document(chunk: VectorChunk) -> Document:
    return Document(
        page_content=chunk.content,
        metadata={
            "chunk_id": chunk.id,
            "document_id": chunk.document_id,
            "page": chunk.page,
            "chunk_index": chunk.chunk_index,
        },
    )
