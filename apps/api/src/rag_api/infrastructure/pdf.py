import re

import fitz

from rag_api.domain.exceptions import DocumentTooManyPages, DocumentWithoutText, InvalidDocument
from rag_api.domain.models import ParsedChunk


def extract_chunks(
    content: bytes,
    *,
    max_pages: int,
    chunk_size: int,
    chunk_overlap: int,
) -> tuple[int, list[ParsedChunk]]:
    try:
        pdf = fitz.open(stream=content, filetype="pdf")
    except (fitz.FileDataError, RuntimeError, ValueError) as exc:
        raise InvalidDocument("上传文件不是可读取的 PDF") from exc

    try:
        page_count = pdf.page_count
        if page_count > max_pages:
            raise DocumentTooManyPages(f"PDF 页数超过 {max_pages} 页限制")

        chunks: list[ParsedChunk] = []
        for page_number, page in enumerate(pdf, start=1):
            text = _normalize_text(page.get_text("text"))
            for segment in _split_text(text, chunk_size, chunk_overlap):
                chunks.append(
                    ParsedChunk(
                        page=page_number,
                        chunk_index=len(chunks),
                        content=segment,
                    )
                )

        if not chunks:
            raise DocumentWithoutText("PDF 中没有可提取的文本")
        return page_count, chunks
    finally:
        pdf.close()


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _split_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    if not text:
        return []

    segments: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            boundary = text.rfind(" ", start + (chunk_size // 2), end)
            if boundary > start:
                end = boundary

        segment = text[start:end].strip()
        if segment:
            segments.append(segment)
        if end >= len(text):
            break
        start = max(end - chunk_overlap, start + 1)
    return segments
