# RAG API

FastAPI backend for document ingestion, retrieval, conversations, and citations.

Current endpoints:

- `GET /health`
- `POST /api/documents`
- `GET /api/documents`
- `DELETE /api/documents/{document_id}`
- `POST /api/conversations`
- `GET /api/conversations/{conversation_id}`
- `POST /api/conversations/{conversation_id}/messages:stream`

Document ingestion persists original PDFs, SQLite metadata, and Chroma chunk vectors under `data/`.
The message endpoint returns Server-Sent Events for tokens and structured citations.

API logs are JSON lines on standard output. Responses include `X-Request-ID`, and error responses
also include `detail`, `error_code`, and `request_id` fields for correlation without exposing
unexpected exception details.
