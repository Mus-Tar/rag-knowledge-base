# RAG Repository Instructions

- This repository contains only the RAG knowledge-base product.
- Keep the FastAPI backend in `apps/api` and the Streamlit frontend in `apps/web`.
- The frontend must communicate with the backend through HTTP/SSE and must not import backend internals.
- Keep runtime dependencies local to each application and shared development tooling at the repository root.
- Do not add the campus activity platform to this repository.
- Do not copy code from `../ref/rag`; use those repositories only as architecture references and respect their licenses.
- Add tests with each behavior change. Tests must not require network access or real model credentials.
