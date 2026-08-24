# RAG Web

Streamlit frontend for the local knowledge base.

The frontend is a thin HTTP client. It does not import or access backend internals.

Current workflow:

- Upload and index one PDF at a time.
- View indexed documents and remove them from all persistent stores.
- Create a conversation and restore its history after a browser refresh.
- Stream answer tokens over SSE.
- Expand structured citations with filename, page number, and source excerpt.
