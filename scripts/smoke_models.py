import logging
import sys
from collections.abc import Callable

from rag_api.config import Settings
from rag_api.domain.models import VectorChunk
from rag_api.infrastructure.embeddings import create_embedding_provider
from rag_api.infrastructure.providers import _create_chat_model
from rag_api.infrastructure.reranking import create_reranker


class SmokeConfigurationError(ValueError):
    pass


def validate_settings(settings: Settings) -> None:
    expected = {
        "llm_provider": ("openai", settings.llm_provider),
        "llm_model": ("deepseek-flash", settings.llm_model),
        "llm_thinking": ("disabled", settings.llm_thinking),
        "embedding_provider": ("openai", settings.embedding_provider),
        "embedding_model": ("BAAI/bge-m3", settings.embedding_model),
        "embedding_dimensions": (1024, settings.embedding_dimensions),
        "reranker_provider": ("siliconflow", settings.reranker_provider),
        "reranker_model": ("BAAI/bge-reranker-v2-m3", settings.reranker_model),
    }
    for name, (required, actual) in expected.items():
        if actual != required:
            raise SmokeConfigurationError(f"RAG_{name.upper()} must be configured for this smoke")

    if not settings.openai_api_key or not settings.openai_base_url:
        raise SmokeConfigurationError("RAG_OPENAI_API_KEY and RAG_OPENAI_BASE_URL are required")
    if not settings.embedding_api_key and not settings.openai_api_key:
        raise SmokeConfigurationError("an embedding API key is required")
    if not settings.embedding_base_url and not settings.openai_base_url:
        raise SmokeConfigurationError("an embedding base URL is required")
    if not settings.reranker_api_key or not settings.reranker_base_url:
        raise SmokeConfigurationError("RAG_RERANKER_API_KEY and RAG_RERANKER_BASE_URL are required")


def _run_stage(name: str, operation: Callable[[], None]) -> bool:
    try:
        operation()
    except Exception as exc:
        print(f"{name}: FAIL ({type(exc).__name__})")
        return False
    print(f"{name}: PASS")
    return True


def _smoke_chat(settings: Settings) -> None:
    response = _create_chat_model(settings).invoke("Reply with one short word: OK")
    if not str(response.content).strip():
        raise RuntimeError("empty model response")
    usage = getattr(response, "usage_metadata", None)
    if usage:
        print(f"  usage={usage}")


def _smoke_embeddings(settings: Settings) -> None:
    vectors = create_embedding_provider(settings).embed(["Offline-independent model smoke"])
    if len(vectors) != 1 or len(vectors[0]) != settings.embedding_dimensions:
        raise RuntimeError("unexpected embedding dimensions")


def _smoke_reranker(settings: Settings) -> None:
    chunks = [
        VectorChunk(
            id=f"smoke-{index}",
            document_id="smoke",
            page=1,
            chunk_index=index,
            content=text,
        )
        for index, text in enumerate(
            ["A short unrelated sample about weather.", "A sample about language models."]
        )
    ]
    ranked = create_reranker(settings).rank("language models", chunks, limit=1)
    if len(ranked) != 1 or ranked[0].id not in {chunk.id for chunk in chunks}:
        raise RuntimeError("unexpected reranker result")


def main() -> int:
    logging.disable(logging.CRITICAL)
    try:
        settings = Settings(_env_file=None)
        validate_settings(settings)
    except SmokeConfigurationError as exc:
        print(f"Configuration: FAIL ({exc})")
        print("Configuration is read from process environment only; .env files are not loaded.")
        return 2
    except Exception as exc:
        print(f"Configuration: FAIL ({type(exc).__name__})")
        print("Configuration is read from process environment only; .env files are not loaded.")
        return 2

    print("Configuration: PASS")
    results = [
        _run_stage("DeepSeek chat", lambda: _smoke_chat(settings)),
        _run_stage("BGE-M3 embeddings", lambda: _smoke_embeddings(settings)),
        _run_stage("SiliconFlow reranker", lambda: _smoke_reranker(settings)),
    ]
    if all(results):
        print("Model smoke: PASS")
        return 0

    print("Model smoke: FAIL", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
