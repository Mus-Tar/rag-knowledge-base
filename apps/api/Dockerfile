FROM python:3.12-slim

ARG UV_VERSION=0.11.32

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN pip install --no-cache-dir "uv==${UV_VERSION}"

COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/web/pyproject.toml apps/web/pyproject.toml

RUN uv sync --frozen --no-dev --package rag-api --no-install-workspace

COPY apps/api/src apps/api/src

RUN uv sync --frozen --no-dev --package rag-api

RUN addgroup --system app && adduser --system --ingroup app app \
    && mkdir -p /app/data \
    && chown -R app:app /app/data

USER app

EXPOSE 8000

CMD ["rag-api"]
