# ruff: noqa: RUF001

from collections.abc import Iterator
from typing import Protocol

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from rag_api.config import Settings
from rag_api.domain.exceptions import DocumentError


class ModelProvider(Protocol):
    supports_query_rewrite: bool

    def stream(self, question: str, context: str) -> Iterator[str]: ...

    def rewrite_query(self, question: str) -> str: ...


class FakeModelProvider:
    supports_query_rewrite = False

    def rewrite_query(self, question: str) -> str:
        return question

    def stream(self, question: str, context: str) -> Iterator[str]:
        if not context.strip():
            yield "当前已索引文档中没有足够证据回答这个问题。"
            return
        yield f"基于检索内容回答：{question}\n\n{context[:500]}"


class LangChainModelProvider:
    supports_query_rewrite = True

    def __init__(self, settings: Settings) -> None:
        model = _create_chat_model(settings)
        answer_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是本地知识库助手。只能根据提供的引用上下文作答。"
                    "若上下文证据不足，请明确回答“当前已索引文档中没有足够证据回答这个问题”，"
                    "不要编造。回答中的每项结论必须能对应至少一条上下文来源。"
                    "使用简洁中文，不要提及未提供的资料。\n\n引用上下文：\n{context}",
                ),
                ("human", "问题：{question}"),
            ]
        )
        rewrite_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "把用户问题改写为简短、可直接用于知识库检索的中文查询。"
                    "只输出查询本身，不要解释，不要回答问题。",
                ),
                ("human", "{question}"),
            ]
        )
        self._answer_chain = answer_prompt | model | StrOutputParser()
        self._rewrite_chain = rewrite_prompt | model | StrOutputParser()

    def stream(self, question: str, context: str) -> Iterator[str]:
        if not context.strip():
            yield "当前已索引文档中没有足够证据回答这个问题。"
            return
        yield from self._answer_chain.stream({"question": question, "context": context})

    def rewrite_query(self, question: str) -> str:
        rewritten = str(self._rewrite_chain.invoke({"question": question})).strip()
        return rewritten[:500] or question


def create_provider(settings: Settings) -> ModelProvider:
    if settings.llm_provider == "fake":
        return FakeModelProvider()
    return LangChainModelProvider(settings)


def _create_chat_model(settings: Settings):
    if settings.llm_provider == "openai":
        if not settings.openai_api_key or not settings.llm_model:
            raise DocumentError("OpenAI 服务需要配置访问密钥和模型名称")
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.llm_model,
            streaming=True,
            timeout=settings.model_timeout_seconds,
            extra_body={"thinking": {"type": settings.llm_thinking}},
        )
    if settings.llm_provider == "ollama":
        if not settings.llm_model:
            raise DocumentError("Ollama 服务需要配置模型名称")
        from langchain_ollama import ChatOllama

        return ChatOllama(base_url=settings.ollama_base_url, model=settings.llm_model)
    raise DocumentError(f"不支持的模型服务：{settings.llm_provider}")
