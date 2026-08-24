import fitz
from fastapi import FastAPI

from rag_api.app import create_app
from rag_api.config import Settings


def make_pdf(*pages: str) -> bytes:
    document = fitz.open()
    try:
        for text in pages:
            page = document.new_page()
            page.insert_text((72, 72), text)
        return document.tobytes()
    finally:
        document.close()


def upload(
    api_request, app: FastAPI, filename: str, content: bytes, content_type: str = "application/pdf"
):
    return api_request(
        app,
        "POST",
        "/api/documents",
        files={"file": (filename, content, content_type)},
    )


def test_upload_list_restart_and_delete_persisted_document(settings: Settings, api_request) -> None:
    source = make_pdf("First page " + ("alpha " * 200), "Second page with durable content")
    app = create_app(settings)

    created = upload(api_request, app, "notes.pdf", source)

    assert created.status_code == 201
    document = created.json()
    assert document["original_filename"] == "notes.pdf"
    assert document["page_count"] == 2
    assert document["chunk_count"] >= 2
    assert document["status"] == "indexed"
    assert app.state.document_service.vector_count() == document["chunk_count"]

    restarted_app = create_app(settings)
    listed = api_request(restarted_app, "GET", "/api/documents")

    assert listed.status_code == 200
    listed_document = listed.json()["documents"][0]
    assert listed_document["id"] == document["id"]
    assert listed_document["sha256"] == document["sha256"]
    assert listed_document["chunk_count"] == document["chunk_count"]
    assert restarted_app.state.document_service.vector_count() == document["chunk_count"]
    assert (settings.uploads_dir / f"{document['id']}.pdf").exists()
    assert settings.database_path.exists()

    deleted = api_request(restarted_app, "DELETE", f"/api/documents/{document['id']}")

    assert deleted.status_code == 204
    assert api_request(restarted_app, "GET", "/api/documents").json() == {"documents": []}
    assert restarted_app.state.document_service.vector_count() == 0
    assert not (settings.uploads_dir / f"{document['id']}.pdf").exists()


def test_duplicate_upload_is_rejected_without_extra_vectors(app: FastAPI, api_request) -> None:
    source = make_pdf("A single indexed document")

    first = upload(api_request, app, "duplicate.pdf", source)
    second = upload(api_request, app, "duplicate.pdf", source)

    assert first.status_code == 201
    assert second.status_code == 409
    assert app.state.document_service.vector_count() == first.json()["chunk_count"]


def test_upload_rejects_non_pdf_and_blank_pdf(app: FastAPI, api_request) -> None:
    invalid = upload(api_request, app, "notes.txt", b"not a PDF", "text/plain")
    invalid_signature = upload(api_request, app, "fake.pdf", b"not a PDF")
    empty_pdf = upload(api_request, app, "empty.pdf", make_pdf(""))

    assert invalid.status_code == 422
    assert invalid_signature.status_code == 422
    assert empty_pdf.status_code == 422


def test_delete_missing_document_returns_not_found(app: FastAPI, api_request) -> None:
    response = api_request(app, "DELETE", "/api/documents/does-not-exist")

    assert response.status_code == 404
