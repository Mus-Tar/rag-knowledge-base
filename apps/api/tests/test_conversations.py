import fitz
from fastapi import FastAPI

from rag_api.app import create_app
from rag_api.config import Settings


def make_pdf(text: str) -> bytes:
    document = fitz.open()
    try:
        page = document.new_page()
        page.insert_text((72, 72), text)
        return document.tobytes()
    finally:
        document.close()


def upload(api_request, app: FastAPI, content: bytes):
    return api_request(
        app,
        "POST",
        "/api/documents",
        files={"file": ("knowledge.pdf", content, "application/pdf")},
    )


def test_sse_answer_contains_tokens_citations_and_persists_messages(
    settings: Settings, api_request
) -> None:
    app = create_app(settings)
    uploaded = upload(api_request, app, make_pdf("Python uses indentation to define code blocks."))
    assert uploaded.status_code == 201

    conversation = api_request(app, "POST", "/api/conversations", json={"title": "Python notes"})
    conversation_id = conversation.json()["id"]
    response = api_request(
        app,
        "POST",
        f"/api/conversations/{conversation_id}/messages:stream",
        json={"question": "How does Python define code blocks?"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert "event: message_start" in body
    assert "event: token" in body
    assert "event: citations" in body
    assert '"filename": "knowledge.pdf"' in body
    assert '"page": 1' in body
    assert "event: message_end" in body

    detail = api_request(app, "GET", f"/api/conversations/{conversation_id}")
    messages = detail.json()["messages"]
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[1]["citations"][0]["filename"] == "knowledge.pdf"


def test_missing_conversation_returns_not_found(settings: Settings, api_request) -> None:
    app = create_app(settings)

    response = api_request(
        app,
        "POST",
        "/api/conversations/does-not-exist/messages:stream",
        json={"question": "hello"},
    )

    assert response.status_code == 404
