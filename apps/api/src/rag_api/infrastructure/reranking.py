import re
from typing import Protocol

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


def create_reranker(settings: Settings) -> Reranker:
    if settings.reranker_provider == "none":
        return NoopReranker()
    if settings.reranker_provider == "lexical":
        return LexicalReranker()
    return BgeReranker(settings.reranker_model)


def _terms(value: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", value.casefold())
