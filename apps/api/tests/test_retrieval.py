from pathlib import Path

from rag_api.domain.models import VectorChunk
from rag_api.infrastructure.vector_store import ChromaVectorStore


def test_feature_hash_vectors_rank_lexically_relevant_chunk_first(tmp_path: Path) -> None:
    store = ChromaVectorStore(tmp_path / "chroma")
    store.add(
        [
            VectorChunk(
                id="python",
                document_id="doc-python",
                page=1,
                chunk_index=0,
                content="Python context managers call __enter__ and __exit__ around a with block.",
            ),
            VectorChunk(
                id="docker",
                document_id="doc-docker",
                page=1,
                chunk_index=0,
                content="Docker Compose healthchecks report whether containers are ready.",
            ),
        ]
    )

    results = store.search("How does a Python context manager exit a with block?", limit=2)

    assert results[0].id == "python"
