from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="RAG_",
        extra="ignore",
    )

    app_name: str = "Local Knowledge Base API"
    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    data_dir: Path = Path("data")
    max_upload_bytes: int = Field(default=20 * 1024 * 1024, ge=1)
    max_pdf_pages: int = Field(default=200, ge=1)
    chunk_size: int = Field(default=800, ge=100)
    chunk_overlap: int = Field(default=120, ge=0)
    llm_provider: Literal["fake", "openai", "ollama"] = "fake"
    llm_model: str = "qwen3:4b"
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    ollama_base_url: str = "http://localhost:11434"
    retrieval_top_k: int = Field(default=4, ge=1, le=20)
    retrieval_candidate_k: int = Field(default=12, ge=1, le=50)
    embedding_provider: Literal["lexical", "ollama", "openai"] = "lexical"
    embedding_model: str = "bge-m3"
    embedding_dimensions: int = Field(default=384, ge=8, le=4096)
    reranker_provider: Literal["none", "lexical", "bge"] = "none"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    query_rewrite_enabled: bool = True
    model_timeout_seconds: float = Field(default=60, gt=0, le=300)
    rate_limit_general: int = Field(default=120, ge=1)
    rate_limit_upload: int = Field(default=12, ge=1)
    rate_limit_chat: int = Field(default=30, ge=1)
    rate_limit_window_seconds: int = Field(default=60, ge=1)

    @model_validator(mode="after")
    def validate_chunking(self) -> "Settings":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        if self.retrieval_candidate_k < self.retrieval_top_k:
            raise ValueError("retrieval_candidate_k must be at least retrieval_top_k")
        return self

    @property
    def index_version(self) -> str:
        raw = f"{self.embedding_provider}-{self.embedding_model}-{self.embedding_dimensions}"
        return "".join(character if character.isalnum() else "-" for character in raw).strip("-")

    @property
    def docs_enabled(self) -> bool:
        return self.app_env != "production"

    @property
    def resolved_data_dir(self) -> Path:
        return self.data_dir.expanduser().resolve()

    @property
    def uploads_dir(self) -> Path:
        return self.resolved_data_dir / "uploads"

    @property
    def chroma_dir(self) -> Path:
        return self.resolved_data_dir / "chroma"

    @property
    def database_path(self) -> Path:
        return self.resolved_data_dir / "rag.db"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path.as_posix()}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
