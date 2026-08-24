import hashlib
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from rag_api.config import Settings
from rag_api.domain.exceptions import (
    DocumentNotFound,
    DocumentTooLarge,
    DuplicateDocument,
    InvalidDocument,
)
from rag_api.domain.models import DocumentSummary, VectorChunk
from rag_api.infrastructure.database import ChunkModel, Database, DocumentModel
from rag_api.infrastructure.pdf import extract_chunks
from rag_api.infrastructure.vector_store import ChromaVectorStore

logger = logging.getLogger(__name__)


class DocumentService:
    def __init__(
        self,
        settings: Settings,
        database: Database,
        vector_store: ChromaVectorStore,
    ) -> None:
        self._settings = settings
        self._database = database
        self._vector_store = vector_store

    def ingest(
        self, *, filename: str | None, content_type: str | None, content: bytes
    ) -> DocumentSummary:
        safe_filename = _validate_upload(
            filename=filename,
            content_type=content_type,
            content=content,
            max_upload_bytes=self._settings.max_upload_bytes,
        )
        page_count, parsed_chunks = extract_chunks(
            content,
            max_pages=self._settings.max_pdf_pages,
            chunk_size=self._settings.chunk_size,
            chunk_overlap=self._settings.chunk_overlap,
        )
        sha256 = hashlib.sha256(content).hexdigest()
        document_id = str(uuid4())
        stored_filename = f"{document_id}.pdf"
        temporary_path = self._settings.uploads_dir / f".{document_id}.uploading"
        final_path = self._settings.uploads_dir / stored_filename
        vector_chunks = [
            VectorChunk(
                id=str(uuid4()),
                document_id=document_id,
                page=chunk.page,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
            )
            for chunk in parsed_chunks
        ]

        self._assert_not_duplicate(sha256)
        temporary_path.write_bytes(content)
        database_created = False
        vectors_created = False
        try:
            self._create_database_document(
                document_id=document_id,
                original_filename=safe_filename,
                stored_filename=stored_filename,
                sha256=sha256,
                page_count=page_count,
                vector_chunks=vector_chunks,
            )
            database_created = True
            self._vector_store.add(vector_chunks)
            vectors_created = True
            os.replace(temporary_path, final_path)
            self._update_status(document_id, "indexed", None)
            logger.info(
                "document_indexed",
                extra={
                    "event": "document_indexed",
                    "document_id": document_id,
                    "page_count": page_count,
                    "chunk_count": len(vector_chunks),
                },
            )
            return self.list_one(document_id)
        except IntegrityError as exc:
            raise DuplicateDocument(document_id) from exc
        except Exception as exc:
            if vectors_created:
                self._vector_store.delete([chunk.id for chunk in vector_chunks])
            if database_created:
                self._update_status(document_id, "failed", str(exc))
            raise
        finally:
            temporary_path.unlink(missing_ok=True)

    def list_documents(self) -> list[DocumentSummary]:
        with self._database.session() as session:
            documents = session.scalars(
                select(DocumentModel).order_by(DocumentModel.created_at.desc())
            ).all()
            return [_to_summary(document) for document in documents]

    def delete(self, document_id: str) -> None:
        with self._database.session() as session:
            document = session.get(DocumentModel, document_id)
            if document is None:
                raise DocumentNotFound("文档不存在")
            vectors = [
                VectorChunk(
                    id=chunk.vector_id,
                    document_id=document.id,
                    page=chunk.page,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                )
                for chunk in document.chunks
            ]
            stored_filename = document.stored_filename

        self._vector_store.delete([chunk.id for chunk in vectors])
        try:
            self._delete_database_document(document_id)
        except Exception:
            self._vector_store.add(vectors)
            raise
        (self._settings.uploads_dir / stored_filename).unlink(missing_ok=True)
        logger.info(
            "document_deleted",
            extra={"event": "document_deleted", "document_id": document_id},
        )

    def vector_count(self) -> int:
        return self._vector_store.count()

    def rebuild(self, document_id: str) -> DocumentSummary:
        with self._database.session() as session:
            document = session.get(DocumentModel, document_id)
            if document is None:
                raise DocumentNotFound("文档不存在")
            source = self._settings.uploads_dir / document.stored_filename
        if not source.exists():
            raise InvalidDocument("文档原始文件不存在, 无法重建索引")
        content = source.read_bytes()
        page_count, parsed_chunks = extract_chunks(
            content,
            max_pages=self._settings.max_pdf_pages,
            chunk_size=self._settings.chunk_size,
            chunk_overlap=self._settings.chunk_overlap,
        )
        chunks = [
            VectorChunk(str(uuid4()), document_id, item.page, item.chunk_index, item.content)
            for item in parsed_chunks
        ]
        self._update_status(document_id, "processing", None)
        old_vector_ids = self._chunk_ids(document_id)
        try:
            self._vector_store.add(chunks)
            with self._database.session() as session:
                model = session.get(DocumentModel, document_id)
                assert model is not None
                model.page_count = page_count
                model.chunk_count = len(chunks)
                model.index_version = self._settings.index_version
                model.status = "indexed"
                model.failure_reason = None
                model.processed_at = datetime.now(UTC)
                model.chunks.clear()
                model.chunks.extend(
                    ChunkModel(
                        id=str(uuid4()),
                        page=chunk.page,
                        chunk_index=chunk.chunk_index,
                        content=chunk.content,
                        vector_id=chunk.id,
                    )
                    for chunk in chunks
                )
                session.commit()
            self._vector_store.delete(old_vector_ids)
        except Exception as exc:
            self._vector_store.delete([chunk.id for chunk in chunks])
            self._update_status(document_id, "failed", str(exc))
            raise
        return self.list_one(document_id)

    def list_one(self, document_id: str) -> DocumentSummary:
        with self._database.session() as session:
            document = session.get(DocumentModel, document_id)
            if document is None:
                raise DocumentNotFound("文档不存在")
            return _to_summary(document)

    def _chunk_ids(self, document_id: str) -> list[str]:
        with self._database.session() as session:
            document = session.get(DocumentModel, document_id)
            return [chunk.vector_id for chunk in document.chunks] if document else []

    def _update_status(self, document_id: str, status: str, failure_reason: str | None) -> None:
        with self._database.session() as session:
            document = session.get(DocumentModel, document_id)
            if document is not None:
                document.status = status
                document.failure_reason = failure_reason
                document.index_version = self._settings.index_version
                if status == "processing":
                    document.processing_started_at = datetime.now(UTC)
                if status in {"completed", "indexed", "failed"}:
                    document.processed_at = datetime.now(UTC)
                session.commit()

    def _assert_not_duplicate(self, sha256: str) -> None:
        with self._database.session() as session:
            existing = session.scalar(
                select(DocumentModel.id).where(DocumentModel.sha256 == sha256)
            )
            if existing is not None:
                raise DuplicateDocument(existing)

    def _create_database_document(
        self,
        *,
        document_id: str,
        original_filename: str,
        stored_filename: str,
        sha256: str,
        page_count: int,
        vector_chunks: list[VectorChunk],
    ) -> DocumentSummary:
        document = DocumentModel(
            id=document_id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            sha256=sha256,
            status="processing",
            index_version=self._settings.index_version,
            processing_started_at=datetime.now(UTC),
            page_count=page_count,
            chunk_count=len(vector_chunks),
            chunks=[
                ChunkModel(
                    id=str(uuid4()),
                    page=chunk.page,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    vector_id=chunk.id,
                )
                for chunk in vector_chunks
            ],
        )
        with self._database.session() as session:
            session.add(document)
            session.commit()
        return _to_summary(document)

    def _delete_database_document(self, document_id: str) -> None:
        with self._database.session() as session:
            document = session.get(DocumentModel, document_id)
            if document is not None:
                session.delete(document)
                session.commit()


def _validate_upload(
    *,
    filename: str | None,
    content_type: str | None,
    content: bytes,
    max_upload_bytes: int,
) -> str:
    if not filename or not filename.lower().endswith(".pdf"):
        raise InvalidDocument("仅支持 PDF 文件")
    if content_type not in {None, "application/pdf", "application/octet-stream"}:
        raise InvalidDocument("上传文件类型必须是 PDF")
    if not content:
        raise InvalidDocument("上传文件为空")
    if len(content) > max_upload_bytes:
        raise DocumentTooLarge(f"上传文件超过 {max_upload_bytes} 字节限制")
    if not content.startswith(b"%PDF-"):
        raise InvalidDocument("上传文件不是有效的 PDF 文件")
    return Path(filename).name


def _to_summary(document: DocumentModel) -> DocumentSummary:
    return DocumentSummary(
        id=document.id,
        original_filename=document.original_filename,
        sha256=document.sha256,
        page_count=document.page_count,
        chunk_count=document.chunk_count,
        status=document.status,
        created_at=document.created_at,
        failure_reason=document.failure_reason,
        index_version=document.index_version,
        processing_started_at=document.processing_started_at,
        processed_at=document.processed_at,
    )
