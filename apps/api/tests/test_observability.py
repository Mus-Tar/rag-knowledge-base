import asyncio
import json
import logging

import httpx
from fastapi import FastAPI

from rag_api.app import create_app
from rag_api.config import Settings
from rag_api.observability import JsonFormatter


def test_request_id_is_echoed_and_errors_are_structured(app: FastAPI, api_request) -> None:
    health = api_request(app, "GET", "/health", headers={"X-Request-ID": "test-request-1"})
    missing = api_request(app, "DELETE", "/api/documents/missing")
    invalid = api_request(app, "POST", "/api/conversations", json={"title": ""})

    assert health.headers["X-Request-ID"] == "test-request-1"
    assert missing.status_code == 404
    assert missing.json()["error_code"] == "not_found"
    assert missing.json()["request_id"] == missing.headers["X-Request-ID"]
    assert invalid.status_code == 422
    assert invalid.json()["error_code"] == "validation_error"
    assert invalid.json()["errors"]


def test_unexpected_error_is_hidden_and_traceable(settings: Settings) -> None:
    app = create_app(settings)

    @app.get("/explode")
    def explode() -> None:
        raise RuntimeError("sensitive internal detail")

    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/explode", headers={"X-Request-ID": "failure-1"})

    response = asyncio.run(send())

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "failure-1"
    assert response.json() == {
        "detail": "服务内部错误, 请稍后重试",
        "error_code": "internal_server_error",
        "request_id": "failure-1",
    }
    assert "sensitive internal detail" not in response.text


def test_json_formatter_emits_machine_readable_fields() -> None:
    record = logging.LogRecord(
        name="rag_api.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="document_indexed",
        args=(),
        exc_info=None,
    )
    record.event = "document_indexed"
    record.request_id = "request-1"
    record.document_id = "document-1"

    payload = json.loads(JsonFormatter().format(record))

    assert payload["level"] == "INFO"
    assert payload["event"] == "document_indexed"
    assert payload["request_id"] == "request-1"
    assert payload["document_id"] == "document-1"
    assert payload["timestamp"].endswith("+00:00")
