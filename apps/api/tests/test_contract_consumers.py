from collections.abc import Iterator

import fitz
import pytest

from rag_api.domain.contracts import (
    UploadEvent,
    UploadState,
    transition_upload_state,
)
from rag_api.infrastructure import pdf


class PdfSpy:
    def __init__(self, document: fitz.Document) -> None:
        self.document = document
        self.closed = False

    @property
    def page_count(self) -> int:
        return self.document.page_count

    def __iter__(self) -> Iterator[fitz.Page]:
        return iter(self.document)

    def close(self) -> None:
        self.document.close()
        self.closed = True


def test_extract_chunks_opens_pdf_once_and_closes_it(monkeypatch: pytest.MonkeyPatch) -> None:
    real_open = fitz.open
    source = real_open()
    page = source.new_page()
    page.insert_text((72, 72), "A paragraph for extraction.")
    content = source.tobytes()
    source.close()

    opened: list[PdfSpy] = []

    def open_spy(*args: object, **kwargs: object) -> PdfSpy:
        spy = PdfSpy(real_open(*args, **kwargs))
        opened.append(spy)
        return spy

    monkeypatch.setattr(pdf.fitz, "open", open_spy)

    page_count, chunks = pdf.extract_chunks(
        content,
        max_pages=10,
        chunk_size=800,
        chunk_overlap=120,
    )

    assert len(opened) == 1
    assert opened[0].closed
    assert page_count == 1
    assert chunks


@pytest.mark.parametrize(
    ("events", "identical_sha256", "expected"),
    [
        (
            [
                UploadEvent.START_PARSING,
                UploadEvent.NO_DUPLICATE,
                UploadEvent.PARTIAL,
                UploadEvent.INDEXED,
            ],
            False,
            UploadState.INDEXED,
        ),
        (
            [
                UploadEvent.START_PARSING,
                UploadEvent.NO_DUPLICATE,
                UploadEvent.PARTIAL,
                UploadEvent.FAILED,
            ],
            False,
            UploadState.FAILED,
        ),
        (
            [
                UploadEvent.START_PARSING,
                UploadEvent.NO_DUPLICATE,
                UploadEvent.INDEXED,
            ],
            False,
            UploadState.INDEXED,
        ),
        (
            [
                UploadEvent.START_PARSING,
                UploadEvent.DUPLICATE_FOUND,
                UploadEvent.KEEP_EXISTING,
            ],
            True,
            UploadState.KEPT_EXISTING,
        ),
        (
            [
                UploadEvent.START_PARSING,
                UploadEvent.DUPLICATE_FOUND,
                UploadEvent.OVERWRITE,
                UploadEvent.INDEXED,
            ],
            False,
            UploadState.INDEXED,
        ),
        (
            [
                UploadEvent.START_PARSING,
                UploadEvent.DUPLICATE_FOUND,
                UploadEvent.KEEP_BOTH,
                UploadEvent.INDEXED,
            ],
            False,
            UploadState.INDEXED,
        ),
    ],
)
def test_upload_state_machine_paths(
    events: list[UploadEvent],
    identical_sha256: bool,
    expected: UploadState,
) -> None:
    current = UploadState.UPLOADED
    for event in events:
        current = transition_upload_state(
            current,
            event,
            identical_sha256=identical_sha256,
        )

    assert current == expected


@pytest.mark.parametrize("event", [UploadEvent.OVERWRITE, UploadEvent.KEEP_BOTH])
def test_identical_hash_only_allows_keep_existing(event: UploadEvent) -> None:
    with pytest.raises(ValueError, match="only allow keep_existing"):
        transition_upload_state(
            UploadState.DUPLICATE_PENDING,
            event,
            identical_sha256=True,
        )


@pytest.mark.parametrize("event", [UploadEvent.OVERWRITE, UploadEvent.KEEP_BOTH])
def test_overwrite_and_keep_both_require_hash_comparison(event: UploadEvent) -> None:
    with pytest.raises(ValueError, match="SHA-256 comparison is required"):
        transition_upload_state(UploadState.DUPLICATE_PENDING, event)
