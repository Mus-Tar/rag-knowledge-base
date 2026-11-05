import json
import logging
from typing import Any

import httpx
import langchain_openai
import pytest
from pydantic import ValidationError

from rag_api.config import Settings
from rag_api.domain.models import VectorChunk
from rag_api.infrastructure import embeddings, reranking
from rag_api.infrastructure.embeddings import OpenAIEmbeddingProvider
from rag_api.infrastructure.providers import _create_chat_model
from rag_api.infrastructure.reranking import SiliconFlowReranker

MODEL_ENV_VARS = (
    "RAG_LLM_PROVIDER",
    "RAG_LLM_MODEL",
    "RAG_LLM_THINKING",
    "RAG_OPENAI_API_KEY",
    "RAG_OPENAI_BASE_URL",
    "RAG_EMBEDDING_PROVIDER",
    "RAG_EMBEDDING_MODEL",
    "RAG_EMBEDDING_DIMENSIONS",
    "RAG_EMBEDDING_API_KEY",
    "RAG_EMBEDDING_BASE_URL",
    "RAG_RERANKER_PROVIDER",
    "RAG_RERANKER_MODEL",
    "RAG_RERANKER_API_KEY",
    "RAG_RERANKER_BASE_URL",
)


@pytest.fixture(autouse=True)
def isolate_model_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in MODEL_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def _install_mock_transport(
    monkeypatch: pytest.MonkeyPatch,
    module: Any,
    transport: httpx.MockTransport,
) -> None:
    original_client = httpx.Client

    def create_client(*, timeout: float) -> httpx.Client:
        return original_client(timeout=timeout, transport=transport)

    monkeypatch.setattr(module.httpx, "Client", create_client)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("embedding_api_key", "unit-test-token"),
        ("embedding_base_url", "https://embedding.invalid/v1"),
    ],
)
def test_embedding_credentials_must_be_configured_together(field: str, value: str) -> None:
    with pytest.raises(ValidationError, match="configured together"):
        Settings(_env_file=None, **{field: value})


def test_embedding_without_specific_credentials_falls_back_to_openai_settings() -> None:
    settings = Settings(
        _env_file=None,
        openai_api_key="legacy-unit-test-token",
        openai_base_url="https://legacy.invalid/v1",
    )

    provider = OpenAIEmbeddingProvider(settings)

    assert provider._api_key == "legacy-unit-test-token"
    assert provider._base_url == "https://legacy.invalid/v1"


@pytest.mark.parametrize(
    ("api_key", "base_url"),
    [
        (None, "https://reranker.invalid/v1"),
        ("unit-test-token", None),
    ],
)
def test_siliconflow_reranker_requires_key_and_base_url(
    api_key: str | None, base_url: str | None
) -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            reranker_provider="siliconflow",
            reranker_api_key=api_key,
            reranker_base_url=base_url,
        )


def test_llm_thinking_defaults_to_disabled() -> None:
    assert Settings.model_construct().llm_thinking == "disabled"


def test_openai_chat_model_disables_thinking_without_logging_key(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    captured: dict[str, Any] = {}

    def fake_chat_openai(**kwargs: Any) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", fake_chat_openai)
    settings = Settings(
        _env_file=None,
        llm_provider="openai",
        llm_model="deepseek-flash",
        openai_api_key="unit-test-token",
        openai_base_url="https://deepseek.invalid",
    )

    with caplog.at_level(logging.DEBUG):
        _create_chat_model(settings)

    assert captured["extra_body"] == {"thinking": {"type": "disabled"}}
    assert "unit-test-token" not in caplog.text


def test_openai_embedding_uses_siliconflow_credentials_and_parses_1024_dimensions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_token = "embedding-unit-test-token"
    request_details: dict[str, Any] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        request_details["url"] = str(request.url)
        request_details["authorization_matches"] = (
            request.headers.get("Authorization") == f"Bearer {test_token}"
        )
        payload = json.loads(request.content)
        request_details["payload"] = payload
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "index": 0,
                        "embedding": [0.125] * 1024,
                    }
                ]
            },
        )

    _install_mock_transport(monkeypatch, embeddings, httpx.MockTransport(handle))
    provider = OpenAIEmbeddingProvider(
        Settings(
            _env_file=None,
            embedding_model="BAAI/bge-m3",
            embedding_dimensions=1024,
            embedding_api_key=test_token,
            embedding_base_url="https://api.siliconflow.cn/v1",
        )
    )

    vectors = provider.embed(["test input"])

    assert request_details["url"] == "https://api.siliconflow.cn/v1/embeddings"
    assert request_details["authorization_matches"]
    assert request_details["payload"] == {
        "model": "BAAI/bge-m3",
        "input": ["test input"],
    }
    assert len(vectors[0]) == 1024
    assert provider.dimensions == 1024


def _chunks() -> list[VectorChunk]:
    return [
        VectorChunk(
            id=f"chunk-{index}",
            document_id="doc-1",
            page=1,
            chunk_index=index,
            content=f"candidate {index}",
        )
        for index in range(3)
    ]


def test_siliconflow_reranker_orders_top_n_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_token = "reranker-unit-test-token"
    request_details: dict[str, Any] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        request_details["url"] = str(request.url)
        request_details["authorization_matches"] = (
            request.headers.get("Authorization") == f"Bearer {test_token}"
        )
        request_details["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 2, "relevance_score": 0.9},
                    {"index": 0, "relevance_score": 0.3},
                ]
            },
        )

    _install_mock_transport(monkeypatch, reranking, httpx.MockTransport(handle))
    chunks = _chunks()
    reranker = SiliconFlowReranker(
        Settings(
            _env_file=None,
            reranker_provider="siliconflow",
            reranker_model="BAAI/bge-reranker-v2-m3",
            reranker_api_key=test_token,
            reranker_base_url="https://api.siliconflow.cn/v1",
        )
    )

    ranked = reranker.rank("question", chunks, limit=2)

    assert request_details["url"] == "https://api.siliconflow.cn/v1/rerank"
    assert request_details["authorization_matches"]
    assert request_details["payload"] == {
        "model": "BAAI/bge-reranker-v2-m3",
        "query": "question",
        "documents": [chunk.content for chunk in chunks],
        "top_n": 2,
        "return_documents": False,
    }
    assert [chunk.id for chunk in ranked] == ["chunk-2", "chunk-0"]


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503),
        httpx.Response(200, json={"results": [{"index": 0, "relevance_score": 0.9}]}),
        httpx.Response(
            200,
            json={
                "results": [
                    {"index": 0, "relevance_score": 0.9},
                    {"index": 0, "relevance_score": 0.8},
                ]
            },
        ),
    ],
)
def test_siliconflow_reranker_rejects_http_or_invalid_results(
    monkeypatch: pytest.MonkeyPatch, response: httpx.Response
) -> None:
    _install_mock_transport(
        monkeypatch,
        reranking,
        httpx.MockTransport(lambda _request: response),
    )
    reranker = SiliconFlowReranker(
        Settings(
            _env_file=None,
            reranker_provider="siliconflow",
            reranker_api_key="unit-test-token",
            reranker_base_url="https://api.siliconflow.cn/v1",
        )
    )

    with pytest.raises(RuntimeError, match="request or response was invalid"):
        reranker.rank("question", _chunks(), limit=2)
