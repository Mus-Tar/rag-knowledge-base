from typing import Protocol

import httpx

from rag_api.config import Settings
from rag_api.infrastructure.lexical import feature_hash_embedding


class EmbeddingProvider(Protocol):
    @property
    def dimensions(self) -> int: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class LexicalEmbeddingProvider:
    def __init__(self, dimensions: int) -> None:
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [feature_hash_embedding(text, self._dimensions) for text in texts]


class OllamaEmbeddingProvider:
    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._model = settings.embedding_model
        self._timeout = settings.model_timeout_seconds
        self._dimensions: int | None = None

    @property
    def dimensions(self) -> int:
        if self._dimensions is None:
            raise RuntimeError("Embedding 维度在首次索引前不可用")
        return self._dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(
                f"{self._base_url}/api/embed", json={"model": self._model, "input": texts}
            )
            response.raise_for_status()
        embeddings = response.json().get("embeddings", [])
        if len(embeddings) != len(texts) or not embeddings:
            raise RuntimeError("Ollama 未返回有效的 Embedding 向量")
        parsed = [[float(value) for value in vector] for vector in embeddings]
        self._dimensions = len(parsed[0])
        if any(len(vector) != self._dimensions for vector in parsed):
            raise RuntimeError("Ollama 返回的 Embedding 向量维度不一致")
        return parsed


class OpenAIEmbeddingProvider:
    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise RuntimeError("OpenAI Embedding 需要配置访问密钥")
        self._api_key = settings.openai_api_key
        self._base_url = (settings.openai_base_url or "https://api.openai.com/v1").rstrip("/")
        self._model = settings.embedding_model
        self._timeout = settings.model_timeout_seconds
        self._dimensions: int | None = None

    @property
    def dimensions(self) -> int:
        if self._dimensions is None:
            raise RuntimeError("Embedding 维度在首次索引前不可用")
        return self._dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(
                f"{self._base_url}/embeddings",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": self._model, "input": texts},
            )
            response.raise_for_status()
        data = sorted(response.json().get("data", []), key=lambda item: item["index"])
        parsed = [[float(value) for value in item["embedding"]] for item in data]
        if len(parsed) != len(texts) or not parsed:
            raise RuntimeError("OpenAI 未返回有效的 Embedding 向量")
        self._dimensions = len(parsed[0])
        return parsed


def create_embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_provider == "lexical":
        return LexicalEmbeddingProvider(settings.embedding_dimensions)
    if settings.embedding_provider == "ollama":
        return OllamaEmbeddingProvider(settings)
    return OpenAIEmbeddingProvider(settings)
