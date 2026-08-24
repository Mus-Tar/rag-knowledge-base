# End-to-end tests

The E2E suite targets a running Docker Compose stack and covers API/Web health, generated PDF
upload, listing, streaming chat, citations, persisted history, and document deletion. The fake
model provider keeps it deterministic and independent of external model credentials.

```powershell
$env:RAG_E2E_API_URL = "http://localhost:8000"
$env:RAG_E2E_WEB_URL = "http://localhost:8501"
uv run pytest -m e2e
```
