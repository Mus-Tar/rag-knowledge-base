# Local Knowledge Base

RAG knowledge-base monorepo with a FastAPI backend and a Streamlit frontend.

## Repository layout

```text
apps/api/   FastAPI service and backend business logic
apps/web/   Streamlit frontend and HTTP API client
tests/e2e/  Cross-application tests
evaluation/ Fixed QA dataset and reproducible retrieval/performance evaluation
docs/       Project-local technical documentation
```

The frontend communicates with the backend only through HTTP. It does not access files, databases, vector stores, or model credentials directly.

## Prerequisites

- Python 3.12 or 3.13
- [uv](https://docs.astral.sh/uv/)
- Docker Desktop, optional

## Local development

Install all workspace and development dependencies:

```powershell
uv sync --all-packages --dev
```

Start the API:

```powershell
uv run --package rag-api rag-api
```

Start the Streamlit frontend in another terminal:

```powershell
uv run --package rag-web rag-web
```

Open `http://localhost:8501`. FastAPI documentation is available at `http://localhost:8000/docs`.

## Quality checks

```powershell
uv run ruff format --check .
uv run ruff check .
uv run pytest
```

## Docker Compose

Start the complete application from a fresh checkout with one command. The default fake model
provider requires no API key and both services wait for their health checks:

```powershell
docker compose up --build --wait
```

The API is exposed on port `8000` and Streamlit on port `8501`.
Copy `.env.example` to `.env` only when you need to override model, chunking, upload, or published
port settings. Stop the stack with `docker compose down`; add `--volumes` to remove persisted data.

## Observability and errors

The API writes one-line JSON logs to standard output for HTTP requests and important document and
conversation events. Every response includes `X-Request-ID`; clients may supply that header to
correlate an error response with container logs. Expected HTTP errors return `detail`, `error_code`,
and `request_id`. Unexpected errors are logged with a traceback while the response hides internal
details.

## Test layers

- Unit and in-process integration tests: `uv run pytest -m "not e2e"`
- Container E2E against a running stack: set the URLs documented in `tests/e2e/README.md`, then run
  `uv run pytest -m e2e`
- Full local quality suite: `uv run ruff format --check .`, `uv run ruff check .`, and
  `uv run pytest --cov`

GitHub Actions runs formatting, lint, unit/integration coverage, Compose build/start, and the full
container E2E workflow. Container logs are printed automatically when a CI step fails.

Validation results and deployment instructions are maintained in [evaluation/report.md](evaluation/report.md)
and [docs/deployment-runbook.md](docs/deployment-runbook.md).

## Current scope

The current implementation provides service startup, health reporting, PDF validation and parsing, chunking, SHA-256 deduplication, SQLite metadata, Chroma persistence, document listing/deletion, LangChain retrieval and model providers, persistent conversations, structured citations, SSE streaming, tests, Docker files, and CI.
