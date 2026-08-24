from typing import Any

import httpx
from pydantic import BaseModel


class ApiUnavailableError(RuntimeError):
    """Raised when the RAG API cannot be reached or returns invalid data."""


class HealthStatus(BaseModel):
    status: str
    service: str
    version: str


class Conversation(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


class Citation(BaseModel):
    document_id: str
    filename: str
    page: int
    chunk_id: str
    excerpt: str


class StreamEvent(BaseModel):
    event: str
    data: dict[str, Any]


class Document(BaseModel):
    id: str
    original_filename: str
    sha256: str
    page_count: int
    chunk_count: int
    status: str
    created_at: str
    failure_reason: str | None = None
    index_version: str | None = None
    processing_started_at: str | None = None
    processed_at: str | None = None


class Message(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    citations: list[Citation]
    created_at: str


class ConversationDetail(Conversation):
    messages: list[Message]


class RagApiClient:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            transport=transport,
        )

    def get_health(self) -> HealthStatus:
        try:
            response = self._client.get("/health")
            response.raise_for_status()
            return HealthStatus.model_validate(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            raise ApiUnavailableError("知识库服务暂时无法连接") from exc

    def list_documents(self) -> list[Document]:
        try:
            response = self._client.get("/api/documents")
            response.raise_for_status()
            return [Document.model_validate(item) for item in response.json()["documents"]]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise ApiUnavailableError("文档列表加载失败") from exc

    def upload_document(self, filename: str, content: bytes, content_type: str) -> Document:
        response: httpx.Response | None = None
        try:
            response = self._client.post(
                "/api/documents",
                files={"file": (filename, content, content_type)},
            )
            response.raise_for_status()
            return Document.model_validate(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            raise ApiUnavailableError(_error_detail(response, "文档上传失败")) from exc

    def delete_document(self, document_id: str) -> None:
        response: httpx.Response | None = None
        try:
            response = self._client.delete(f"/api/documents/{document_id}")
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ApiUnavailableError(_error_detail(response, "文档删除失败")) from exc

    def rebuild_document(self, document_id: str) -> Document:
        response: httpx.Response | None = None
        try:
            response = self._client.post(f"/api/documents/{document_id}/rebuild")
            response.raise_for_status()
            return Document.model_validate(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            raise ApiUnavailableError(_error_detail(response, "文档重建索引失败")) from exc

    def batch_delete_documents(self, document_ids: list[str]) -> None:
        response: httpx.Response | None = None
        try:
            response = self._client.post(
                "/api/documents/batch-delete", json={"document_ids": document_ids}
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ApiUnavailableError(_error_detail(response, "批量删除文档失败")) from exc

    def batch_rebuild_documents(self, document_ids: list[str]) -> list[Document]:
        response: httpx.Response | None = None
        try:
            response = self._client.post(
                "/api/documents/batch-rebuild", json={"document_ids": document_ids}
            )
            response.raise_for_status()
            return [Document.model_validate(item) for item in response.json()["documents"]]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise ApiUnavailableError(_error_detail(response, "批量重建索引失败")) from exc

    def create_conversation(self, title: str = "新对话") -> Conversation:
        try:
            response = self._client.post("/api/conversations", json={"title": title})
            response.raise_for_status()
            return Conversation.model_validate(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            raise ApiUnavailableError("新建对话失败") from exc

    def get_conversation(self, conversation_id: str) -> ConversationDetail:
        response: httpx.Response | None = None
        try:
            response = self._client.get(f"/api/conversations/{conversation_id}")
            response.raise_for_status()
            return ConversationDetail.model_validate(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            raise ApiUnavailableError(_error_detail(response, "对话记录加载失败")) from exc

    def list_conversations(self) -> list[Conversation]:
        try:
            response = self._client.get("/api/conversations")
            response.raise_for_status()
            return [Conversation.model_validate(item) for item in response.json()["conversations"]]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise ApiUnavailableError("对话列表加载失败") from exc

    def rename_conversation(self, conversation_id: str, title: str) -> Conversation:
        response: httpx.Response | None = None
        try:
            response = self._client.patch(
                f"/api/conversations/{conversation_id}", json={"title": title}
            )
            response.raise_for_status()
            return Conversation.model_validate(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            raise ApiUnavailableError(_error_detail(response, "对话重命名失败")) from exc

    def delete_conversation(self, conversation_id: str) -> None:
        response: httpx.Response | None = None
        try:
            response = self._client.delete(f"/api/conversations/{conversation_id}")
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ApiUnavailableError(_error_detail(response, "对话删除失败")) from exc

    def stream_message(self, conversation_id: str, question: str):
        try:
            with self._client.stream(
                "POST",
                f"/api/conversations/{conversation_id}/messages:stream",
                json={"question": question},
            ) as response:
                response.raise_for_status()
                event_name = "message"
                data_lines: list[str] = []
                for line in response.iter_lines():
                    if not line:
                        if data_lines:
                            import json

                            yield StreamEvent(
                                event=event_name, data=json.loads("\n".join(data_lines))
                            )
                            data_lines = []
                        continue
                    if line.startswith("event: "):
                        event_name = line[7:]
                    elif line.startswith("data: "):
                        data_lines.append(line[6:])
        except (httpx.HTTPError, ValueError) as exc:
            raise ApiUnavailableError("回答流式传输失败") from exc

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "RagApiClient":
        return self

    def __exit__(self, *_exc_info: Any) -> None:
        self.close()


def _error_detail(response: httpx.Response | None, fallback: str) -> str:
    if response is None:
        return fallback
    try:
        detail = response.json().get("detail")
    except (ValueError, TypeError):
        detail = None
    return str(detail or fallback)
