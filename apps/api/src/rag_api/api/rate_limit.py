# ruff: noqa: RUF001

from fastapi import HTTPException, Request, status

from rag_api.config import Settings
from rag_api.metrics import IpRateLimiter


def enforce_rate_limit(request: Request, category: str) -> None:
    settings: Settings = request.app.state.settings
    limiter: IpRateLimiter = request.app.state.rate_limiter
    limits = {
        "general": settings.rate_limit_general,
        "upload": settings.rate_limit_upload,
        "chat": settings.rate_limit_chat,
    }
    client_ip = request.client.host if request.client else "unknown"
    retry_after = limiter.allow(
        client_ip, category, limits[category], settings.rate_limit_window_seconds
    )
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="请求过于频繁，请稍后再试",
            headers={"Retry-After": str(retry_after)},
        )
