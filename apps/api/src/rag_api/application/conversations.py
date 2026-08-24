# ruff: noqa: RUF001

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import uuid4

from langchain_core.documents import Document
from sqlalchemy import select

from rag_api.config import Settings
from rag_api.domain.exceptions import DocumentNotFound
from rag_api.domain.models import Citation, ConversationSummary, MessageSummary, RetrievalMetadata
from rag_api.infrastructure.database import ConversationModel, Database, DocumentModel, MessageModel
from rag_api.infrastructure.providers import ModelProvider
from rag_api.infrastructure.retrieval import ChromaRetriever

logger = logging.getLogger(__name__)


class ConversationService:
    def __init__(
        self,
        settings: Settings,
        database: Database,
        retriever: ChromaRetriever,
        provider: ModelProvider,
    ) -> None:
        self._settings = settings
        self._database = database
        self._retriever = retriever
        self._provider = provider

    def create(self, title: str = "新对话") -> ConversationSummary:
        conversation = ConversationModel(id=str(uuid4()), title=title[:255])
        with self._database.session() as session:
            session.add(conversation)
            session.commit()
        return _conversation_summary(conversation)

    def list(self) -> list[ConversationSummary]:
        with self._database.session() as session:
            return [
                _conversation_summary(item)
                for item in session.scalars(
                    select(ConversationModel).order_by(ConversationModel.updated_at.desc())
                )
            ]

    def rename(self, conversation_id: str, title: str) -> ConversationSummary:
        with self._database.session() as session:
            conversation = session.get(ConversationModel, conversation_id)
            if conversation is None:
                raise DocumentNotFound("对话不存在")
            conversation.title = title[:255]
            conversation.updated_at = datetime.now(UTC)
            session.commit()
            return _conversation_summary(conversation)

    def delete(self, conversation_id: str) -> None:
        with self._database.session() as session:
            conversation = session.get(ConversationModel, conversation_id)
            if conversation is None:
                raise DocumentNotFound("对话不存在")
            session.delete(conversation)
            session.commit()

    def get(self, conversation_id: str) -> tuple[ConversationSummary, list[MessageSummary]]:
        with self._database.session() as session:
            conversation = session.get(ConversationModel, conversation_id)
            if conversation is None:
                raise DocumentNotFound("对话不存在")
            return _conversation_summary(conversation), [
                _message_summary(message) for message in conversation.messages
            ]

    def stream_answer(
        self, conversation_id: str, question: str
    ) -> tuple[str, list[Citation], RetrievalMetadata, Iterator[str]]:
        self._assert_conversation(conversation_id)
        retrieval_query = question
        if self._settings.query_rewrite_enabled and self._provider.supports_query_rewrite:
            try:
                retrieval_query = self._provider.rewrite_query(question)
            except Exception:
                logger.warning(
                    "query_rewrite_failed",
                    extra={"event": "query_rewrite_failed", "conversation_id": conversation_id},
                )
        documents, retrieval = self._retriever.retrieve(retrieval_query)
        citations = self._citations(documents)
        context = "\n\n".join(
            f"[来源：第 {document.metadata['page']} 页] {document.page_content}"
            for document in documents
        )
        tokens = self._provider.stream(question, context)
        message_id = str(uuid4())

        def persist_and_stream() -> Iterator[str]:
            parts: list[str] = []
            try:
                for token in tokens:
                    parts.append(token)
                    yield token
            finally:
                self._save_messages(conversation_id, question, "".join(parts), citations)

        return message_id, citations, retrieval, persist_and_stream()

    def _assert_conversation(self, conversation_id: str) -> None:
        with self._database.session() as session:
            if session.get(ConversationModel, conversation_id) is None:
                raise DocumentNotFound("对话不存在")

    def _citations(self, documents: list[Document]) -> list[Citation]:
        document_ids = {str(document.metadata["document_id"]) for document in documents}
        with self._database.session() as session:
            names = {
                document.id: document.original_filename
                for document in session.scalars(
                    select(DocumentModel).where(DocumentModel.id.in_(document_ids))
                )
            }
        return [
            Citation(
                document_id=str(document.metadata["document_id"]),
                filename=names.get(str(document.metadata["document_id"]), "unknown.pdf"),
                page=int(document.metadata["page"]),
                chunk_id=str(document.metadata["chunk_id"]),
                excerpt=document.page_content,
            )
            for document in documents
        ]

    def _save_messages(
        self, conversation_id: str, question: str, answer: str, citations: list[Citation]
    ) -> None:
        now = datetime.now(UTC)
        with self._database.session() as session:
            conversation = session.get(ConversationModel, conversation_id)
            if conversation is None:
                return
            session.add(
                MessageModel(
                    id=str(uuid4()),
                    conversation_id=conversation_id,
                    role="user",
                    content=question,
                    citations="[]",
                    created_at=now,
                )
            )
            session.add(
                MessageModel(
                    id=str(uuid4()),
                    conversation_id=conversation_id,
                    role="assistant",
                    content=answer,
                    citations=json.dumps(
                        [citation.__dict__ for citation in citations], ensure_ascii=False
                    ),
                    created_at=now,
                )
            )
            conversation.updated_at = now
            session.commit()
        logger.info(
            "answer_persisted",
            extra={
                "event": "answer_persisted",
                "conversation_id": conversation_id,
                "citation_count": len(citations),
            },
        )


def _conversation_summary(model: ConversationModel) -> ConversationSummary:
    return ConversationSummary(model.id, model.title, model.created_at, model.updated_at)


def _message_summary(model: MessageModel) -> MessageSummary:
    raw_citations = json.loads(model.citations)
    return MessageSummary(
        model.id,
        model.conversation_id,
        model.role,
        model.content,
        [Citation(**citation) for citation in raw_citations],
        model.created_at,
    )
