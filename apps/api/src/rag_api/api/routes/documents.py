from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from pydantic import BaseModel

from rag_api.api.dependencies import get_document_service
from rag_api.api.rate_limit import enforce_rate_limit
from rag_api.application.documents import DocumentService
from rag_api.domain.exceptions import (
    DocumentError,
    DocumentNotFound,
    DocumentTooLarge,
    DuplicateDocument,
)
from rag_api.domain.models import DocumentSummary

router = APIRouter(prefix="/api/documents", tags=["documents"])


class DocumentResponse(BaseModel):
    id: str
    original_filename: str
    sha256: str
    page_count: int
    chunk_count: int
    status: str
    created_at: datetime
    failure_reason: str | None = None
    index_version: str | None = None
    processing_started_at: datetime | None = None
    processed_at: datetime | None = None


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]


class BatchDocumentRequest(BaseModel):
    document_ids: list[str]


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    service: DocumentService = Depends(get_document_service),
) -> DocumentResponse:
    try:
        enforce_rate_limit(request, "upload")
        document = service.ingest(
            filename=file.filename,
            content_type=file.content_type,
            content=await _read_limited(file, request.app.state.settings.max_upload_bytes),
        )
        return _to_response(document)
    except DocumentError as exc:
        raise _document_http_error(exc) from exc
    finally:
        await file.close()


@router.get("", response_model=DocumentListResponse)
def list_documents(
    request: Request,
    service: DocumentService = Depends(get_document_service),
) -> DocumentListResponse:
    enforce_rate_limit(request, "general")
    return DocumentListResponse(
        documents=[_to_response(document) for document in service.list_documents()]
    )


@router.post("/batch-delete", status_code=status.HTTP_204_NO_CONTENT)
def batch_delete_documents(
    payload: BatchDocumentRequest,
    request: Request,
    service: DocumentService = Depends(get_document_service),
) -> Response:
    enforce_rate_limit(request, "general")
    for document_id in payload.document_ids:
        service.delete(document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/batch-rebuild", response_model=DocumentListResponse)
def batch_rebuild_documents(
    payload: BatchDocumentRequest,
    request: Request,
    service: DocumentService = Depends(get_document_service),
) -> DocumentListResponse:
    enforce_rate_limit(request, "upload")
    return DocumentListResponse(
        documents=[
            _to_response(service.rebuild(document_id)) for document_id in payload.document_ids
        ]
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: str,
    request: Request,
    service: DocumentService = Depends(get_document_service),
) -> Response:
    enforce_rate_limit(request, "general")
    try:
        service.delete(document_id)
    except DocumentError as exc:
        raise _document_http_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{document_id}/rebuild", response_model=DocumentResponse)
def rebuild_document(
    document_id: str,
    request: Request,
    service: DocumentService = Depends(get_document_service),
) -> DocumentResponse:
    enforce_rate_limit(request, "upload")
    try:
        return _to_response(service.rebuild(document_id))
    except DocumentError as exc:
        raise _document_http_error(exc) from exc


def _to_response(document: DocumentSummary) -> DocumentResponse:
    return DocumentResponse(**document.__dict__)


def _document_http_error(error: DocumentError) -> HTTPException:
    if isinstance(error, DuplicateDocument):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    if isinstance(error, DocumentNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    if isinstance(error, DocumentTooLarge):
        return HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=str(error))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


async def _read_limited(file: UploadFile, max_upload_bytes: int) -> bytes:
    chunks: list[bytes] = []
    received = 0
    while content := await file.read(1024 * 1024):
        received += len(content)
        if received > max_upload_bytes:
            raise DocumentTooLarge(f"上传文件超过 {max_upload_bytes} 字节限制")
        chunks.append(content)
    return b"".join(chunks)
