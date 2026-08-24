from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings

from rag_api.domain.models import VectorChunk
from rag_api.infrastructure.embeddings import EmbeddingProvider, LexicalEmbeddingProvider
from rag_api.infrastructure.lexical import dot, feature_hash_embedding


class ChromaVectorStore:
    def __init__(
        self,
        path: Path,
        embedding_provider: EmbeddingProvider | None = None,
        index_version: str = "lexical-feature-hash-384",
    ) -> None:
        path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=str(path), settings=ChromaSettings(anonymized_telemetry=False)
        )
        self._embedding_provider = embedding_provider or LexicalEmbeddingProvider(384)
        self.index_version = index_version
        self.collection_name = f"document_chunks_{index_version}"[:63]
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name, embedding_function=None
        )

    def add(self, chunks: list[VectorChunk]) -> None:
        if not chunks:
            return
        self._collection.add(
            ids=[chunk.id for chunk in chunks],
            documents=[chunk.content for chunk in chunks],
            metadatas=[
                {
                    "document_id": chunk.document_id,
                    "page": chunk.page,
                    "chunk_index": chunk.chunk_index,
                    "index_version": self.index_version,
                }
                for chunk in chunks
            ],
            embeddings=self._embedding_provider.embed([chunk.content for chunk in chunks]),
        )

    def delete(self, ids: list[str]) -> None:
        if not ids:
            return
        for collection in self._client.list_collections():
            if collection.name.startswith("document_chunks_"):
                collection.delete(ids=ids)

    def count(self) -> int:
        return self._collection.count()

    def search(self, query: str, limit: int) -> list[VectorChunk]:
        if self._collection.count() == 0:
            return []
        result = self._collection.query(
            query_embeddings=self._embedding_provider.embed([query]),
            n_results=min(limit, self._collection.count()),
            include=["documents", "metadatas"],
        )
        return _to_chunks(result)

    def lexical_search(self, query: str, limit: int) -> list[VectorChunk]:
        if self._collection.count() == 0:
            return []
        result = self._collection.get(include=["documents", "metadatas"])
        chunks = _to_chunks(result)
        query_vector = feature_hash_embedding(query, 384)
        return sorted(
            chunks,
            key=lambda chunk: dot(query_vector, feature_hash_embedding(chunk.content, 384)),
            reverse=True,
        )[:limit]


def _to_chunks(result: dict) -> list[VectorChunk]:
    ids = result.get("ids", [])
    documents = result.get("documents", [])
    metadatas = result.get("metadatas", [])
    if ids and isinstance(ids[0], list):
        ids, documents, metadatas = ids[0], documents[0], metadatas[0]
    return [
        VectorChunk(
            id=str(chunk_id),
            document_id=str(metadata["document_id"]),
            page=int(metadata["page"]),
            chunk_index=int(metadata["chunk_index"]),
            content=str(document),
        )
        for chunk_id, document, metadata in zip(ids, documents, metadatas, strict=True)
    ]
