import math
import re
from typing import Protocol

import httpx

from rag_api.config import Settings
from rag_api.domain.models import VectorChunk


class Reranker(Protocol):
    def rank(self, query: str, chunks: list[VectorChunk], limit: int) -> list[VectorChunk]: ...


class NoopReranker:
    def rank(self, query: str, chunks: list[VectorChunk], limit: int) -> list[VectorChunk]:
        return chunks[:limit]


class LexicalReranker:
    def rank(self, query: str, chunks: list[VectorChunk], limit: int) -> list[VectorChunk]:
        terms = set(_terms(query))
        return sorted(
            chunks,
            key=lambda chunk: len(terms & set(_terms(chunk.content))),
            reverse=True,
        )[:limit]


class BgeReranker:
    def __init__(self, model_name: str) -> None:
        try:
            from FlagEmbedding import FlagReranker
        except ImportError as exc:
            raise RuntimeError(
                "BGE 重排序组件未安装。请安装 rag-api 的 rerank 可选依赖后重试"
            ) from exc
        self._model = FlagReranker(model_name, use_fp16=False)

    def rank(self, query: str, chunks: list[VectorChunk], limit: int) -> list[VectorChunk]:
        scores = self._model.compute_score([[query, chunk.content] for chunk in chunks])
        return [
            chunk
            for _, chunk in sorted(
                zip(scores, chunks, strict=True), key=lambda item: item[0], reverse=True
            )
        ][:limit]


class SiliconFlowReranker:
    def __init__(self, settings: Settings) -> None:
        if not settings.reranker_api_key or not settings.reranker_base_url:
            raise RuntimeError("SiliconFlow Reranker 需要配置访问密钥和 Base URL")
        self._api_key = settings.reranker_api_key
        self._base_url = settings.reranker_base_url.rstrip("/")
        self._model = settings.reranker_model
        self._timeout = settings.model_timeout_seconds

    def rank(self, query: str, chunks: list[VectorChunk], limit: int) -> list[VectorChunk]:
        if not chunks or limit <= 0:
            return []

        expected_count = min(limit, len(chunks))
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    f"{self._base_url}/rerank",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={
                        "model": self._model,
                        "query": query,
                        "documents": [chunk.content for chunk in chunks],
                        "top_n": limit,
                        "return_documents": False,
                    },
                )
                response.raise_for_status()
                results = response.json()["results"]
            if not isinstance(results, list) or len(results) != expected_count:
                raise ValueError("unexpected rerank result count")

            ranked: list[tuple[float, int]] = []
            seen_indices: set[int] = set()
            for result in results:
                index = result["index"]
                if isinstance(index, bool) or not isinstance(index, int):
                    raise ValueError("rerank result index must be an integer")
                if index < 0 or index >= len(chunks) or index in seen_indices:
                    raise ValueError("rerank result index is invalid or duplicated")
                score = float(result["relevance_score"])
                if not math.isfinite(score):
                    raise ValueError("rerank result score must be finite")
                seen_indices.add(index)
                ranked.append((score, index))
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("SiliconFlow Reranker request or response was invalid") from exc

        ranked.sort(key=lambda item: item[0], reverse=True)
        return [chunks[index] for _, index in ranked[:limit]]


def create_reranker(settings: Settings) -> Reranker:
    if settings.reranker_provider == "none":
        return NoopReranker()
    if settings.reranker_provider == "lexical":
        return LexicalReranker()
    if settings.reranker_provider == "bge":
        return BgeReranker(settings.reranker_model)
    if settings.reranker_provider == "siliconflow":
        return SiliconFlowReranker(settings)
    raise ValueError(f"不支持的重排服务: {settings.reranker_provider}")


def _terms(value: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", value.casefold())
