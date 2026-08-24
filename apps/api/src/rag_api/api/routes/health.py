from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from rag_api import __version__

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="rag-api",
        version=__version__,
    )
