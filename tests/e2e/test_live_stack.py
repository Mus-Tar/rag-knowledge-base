import os
from uuid import uuid4

import fitz
import httpx
import pytest

pytestmark = pytest.mark.e2e


def _pdf_bytes(text: str) -> bytes:
    document = fitz.open()
    try:
        page = document.new_page()
        page.insert_text((72, 72), text)
        return document.tobytes()
    finally:
        document.close()


def test_complete_browser_backed_api_workflow() -> None:
    api_url = os.environ.get("RAG_E2E_API_URL")
    web_url = os.environ.get("RAG_E2E_WEB_URL")
    if not api_url or not web_url:
        pytest.skip("RAG_E2E_API_URL and RAG_E2E_WEB_URL must target a running stack")

    marker = uuid4().hex
    filename = f"e2e-{marker}.pdf"
    content = _pdf_bytes(f"Python context managers reliably release resources. {marker}")

    with httpx.Client(timeout=30) as client:
        api_health = client.get(f"{api_url}/health")
        web_health = client.get(f"{web_url}/_stcore/health")
        assert api_health.status_code == 200
        assert api_health.json()["status"] == "ok"
        assert web_health.status_code == 200
        assert web_health.text == "ok"

        uploaded = client.post(
            f"{api_url}/api/documents",
            files={"file": (filename, content, "application/pdf")},
        )
        assert uploaded.status_code == 201, uploaded.text
        document = uploaded.json()

        try:
            listed = client.get(f"{api_url}/api/documents")
            assert any(item["id"] == document["id"] for item in listed.json()["documents"])

            created = client.post(
                f"{api_url}/api/conversations",
                json={"title": "Container E2E"},
            )
            assert created.status_code == 201, created.text
            conversation_id = created.json()["id"]

            answer = client.post(
                f"{api_url}/api/conversations/{conversation_id}/messages:stream",
                json={"question": "What do Python context managers do?"},
            )
            assert answer.status_code == 200, answer.text
            assert "event: token" in answer.text
            assert "event: citations" in answer.text
            assert f'"filename": "{filename}"' in answer.text

            history = client.get(f"{api_url}/api/conversations/{conversation_id}")
            assert history.status_code == 200
            assert [message["role"] for message in history.json()["messages"]] == [
                "user",
                "assistant",
            ]
        finally:
            deleted = client.delete(f"{api_url}/api/documents/{document['id']}")
            assert deleted.status_code == 204
