import asyncio
from collections.abc import Generator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from rag_api.app import create_app
from rag_api.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(app_env="test", data_dir=tmp_path / "data")


@pytest.fixture
def app(settings: Settings) -> Generator[FastAPI, None, None]:
    yield create_app(settings)


@pytest.fixture
def api_request():
    def request(app: FastAPI, method: str, path: str, **kwargs: Any) -> httpx.Response:
        async def send() -> httpx.Response:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                return await client.request(method, path, **kwargs)

        return asyncio.run(send())

    return request
