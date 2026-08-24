import httpx
import pytest

from rag_web.api_client import ApiUnavailableError, RagApiClient


def test_get_health_parses_api_response() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            status_code=200,
            json={"status": "ok", "service": "rag-api", "version": "0.1.0"},
        )
    )

    with RagApiClient("http://api.test", 1, transport=transport) as client:
        health = client.get_health()

    assert health.status == "ok"
    assert health.service == "rag-api"
    assert health.version == "0.1.0"


def test_get_health_maps_http_errors_to_domain_error() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(status_code=503, json={"detail": "down"})
    )

    with (
        RagApiClient("http://api.test", 1, transport=transport) as client,
        pytest.raises(ApiUnavailableError, match="知识库服务暂时无法连接"),
    ):
        client.get_health()


def test_document_operations_and_conversation_history() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/api/documents":
            return httpx.Response(
                200,
                json={
                    "documents": [
                        {
                            "id": "doc-1",
                            "original_filename": "guide.pdf",
                            "sha256": "abc",
                            "page_count": 2,
                            "chunk_count": 3,
                            "status": "indexed",
                            "created_at": "2026-07-25T00:00:00Z",
                        }
                    ]
                },
            )
        if request.method == "POST" and request.url.path == "/api/documents":
            assert b"guide.pdf" in request.content
            return httpx.Response(
                201,
                json={
                    "id": "doc-1",
                    "original_filename": "guide.pdf",
                    "sha256": "abc",
                    "page_count": 2,
                    "chunk_count": 3,
                    "status": "indexed",
                    "created_at": "2026-07-25T00:00:00Z",
                },
            )
        if request.method == "DELETE":
            return httpx.Response(204)
        if request.method == "POST" and request.url.path == "/api/conversations":
            return httpx.Response(
                201,
                json={
                    "id": "conversation-1",
                    "title": "New",
                    "created_at": "2026-07-25T00:00:00Z",
                    "updated_at": "2026-07-25T00:00:00Z",
                },
            )
        if request.method == "GET" and request.url.path == "/api/conversations/conversation-1":
            return httpx.Response(
                200,
                json={
                    "id": "conversation-1",
                    "title": "New",
                    "created_at": "2026-07-25T00:00:00Z",
                    "updated_at": "2026-07-25T00:00:00Z",
                    "messages": [],
                },
            )
        raise AssertionError(f"Unhandled request: {request.method} {request.url}")

    with RagApiClient("http://api.test", 1, transport=httpx.MockTransport(handler)) as client:
        documents = client.list_documents()
        uploaded = client.upload_document("guide.pdf", b"pdf-content", "application/pdf")
        client.delete_document(uploaded.id)
        conversation = client.create_conversation("New")
        detail = client.get_conversation(conversation.id)

    assert documents[0].original_filename == "guide.pdf"
    assert uploaded.id == "doc-1"
    assert detail.messages == []


def test_stream_message_parses_sse_events() -> None:
    body = (
        'event: message_start\ndata: {"message_id":"message-1"}\n\n'
        'event: token\ndata: {"text":"hello"}\n\n'
        'event: citations\ndata: {"items":[]}\n\n'
        'event: message_end\ndata: {"message_id":"message-1"}\n\n'
    )
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, text=body))

    with RagApiClient("http://api.test", 1, transport=transport) as client:
        events = list(client.stream_message("conversation-1", "question"))

    assert [event.event for event in events] == [
        "message_start",
        "token",
        "citations",
        "message_end",
    ]
    assert events[1].data["text"] == "hello"
