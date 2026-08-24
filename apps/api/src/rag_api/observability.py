import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request, Response

from rag_api.metrics import Metrics

request_id_context: ContextVar[str] = ContextVar("request_id", default="-")

_LOG_FIELDS = (
    "event",
    "request_id",
    "method",
    "path",
    "status_code",
    "duration_ms",
    "document_id",
    "conversation_id",
    "page_count",
    "chunk_count",
    "citation_count",
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in _LOG_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if "request_id" not in payload:
            payload["request_id"] = request_id_context.get()
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(level.upper())
    logging.captureWarnings(True)

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True


def install_request_logging(app: FastAPI) -> None:
    logger = logging.getLogger("rag_api.requests")

    @app.middleware("http")
    async def log_request(request: Request, call_next) -> Response:
        supplied_request_id = request.headers.get("X-Request-ID", "").strip()
        request_id = supplied_request_id if 0 < len(supplied_request_id) <= 128 else uuid4().hex
        request.state.request_id = request_id
        token = request_id_context.set(request_id)
        started_at = perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_context.reset(token)

        duration_ms = round((perf_counter() - started_at) * 1000, 2)
        metrics: Metrics = app.state.metrics
        metrics.observe_request(request.url.path, response.status_code, duration_ms / 1000)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_completed",
            extra={
                "event": "request_completed",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response
