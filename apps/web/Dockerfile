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

RUN uv sync --frozen --no-dev --package rag-web --no-install-workspace

COPY apps/web/src apps/web/src

RUN uv sync --frozen --no-dev --package rag-web

RUN addgroup --system app && adduser --system --ingroup app app

USER app

EXPOSE 8501

CMD ["rag-web"]
