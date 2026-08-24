# Deployment and Runbook

## Local/CI Deployment

The supported deployment target is the two-service Docker Compose stack in `compose.yaml`.
The API owns SQLite, uploaded PDFs, and Chroma data on the named `rag-data` volume. The Streamlit
container communicates with the API over HTTP/SSE and does not access that volume.

```powershell
docker compose up --detach --build --wait
```

The default `fake` provider is offline and requires no credentials. Published ports can be changed
with `RAG_API_PUBLISHED_PORT` and `RAG_WEB_PUBLISHED_PORT`; model/provider settings are documented
in `.env.example`. Check status with `docker compose ps` and stop with:

```powershell
docker compose down
```

Use `docker compose down --volumes` only when intentionally deleting the persisted knowledge base.

## Health and Logs

- API health: `GET http://localhost:8000/health`
- Streamlit health: `GET http://localhost:8501/_stcore/health`
- Container logs: `docker compose logs --follow`

API logs are one-line JSON. Every response carries `X-Request-ID`; pass that value to support
correlation between an error response and request logs.

## Verified Run

On 2026-07-25, a fresh Compose build was started with `docker compose up --detach --build --wait`.
Both containers reached `healthy`, and the container E2E workflow passed for upload, list, SSE
answer, citations, conversation history, and delete. The fixed evaluation then completed 10 uploads
and 20 questions in 4.93 seconds wall-clock time; its detailed metrics are in
`evaluation/results/run-2026-07-25.json`.

GitHub Actions repeats formatting, lint, unit/integration coverage, Compose build/start, and the
same container E2E flow on every push to `main` and every pull request. Failed runs collect Compose
logs before teardown.
