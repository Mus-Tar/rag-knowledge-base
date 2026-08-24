import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("rag_api.errors")


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return _error_response(
            request,
            status_code=exc.status_code,
            detail=str(exc.detail),
            error_code=_http_error_code(exc.status_code),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _error_response(
            request,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="请求参数校验失败",
            error_code="validation_error",
            errors=jsonable_encoder(exc.errors()),
        )

    @app.exception_handler(Exception)
    async def unexpected_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = _request_id(request)
        logger.exception(
            "unhandled_exception",
            extra={
                "event": "unhandled_exception",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
            },
        )
        return _error_response(
            request,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="服务内部错误, 请稍后重试",
            error_code="internal_server_error",
        )


def _error_response(
    request: Request,
    *,
    status_code: int,
    detail: str,
    error_code: str,
    headers: dict[str, str] | None = None,
    errors: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    request_id = _request_id(request)
    content: dict[str, Any] = {
        "detail": detail,
        "error_code": error_code,
        "request_id": request_id,
    }
    if errors is not None:
        content["errors"] = errors
    response_headers = dict(headers or {})
    response_headers["X-Request-ID"] = request_id
    return JSONResponse(status_code=status_code, content=content, headers=response_headers)


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "-")


def _http_error_code(status_code: int) -> str:
    return {
        status.HTTP_404_NOT_FOUND: "not_found",
        status.HTTP_409_CONFLICT: "conflict",
        status.HTTP_413_CONTENT_TOO_LARGE: "payload_too_large",
        status.HTTP_422_UNPROCESSABLE_CONTENT: "unprocessable_content",
    }.get(status_code, "http_error")
