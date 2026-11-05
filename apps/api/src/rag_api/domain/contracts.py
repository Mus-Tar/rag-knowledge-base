import re
from collections.abc import Sequence
from dataclasses import dataclass, field, fields
from enum import StrEnum
from typing import Literal

BlockType = Literal[
    "title", "paragraph", "table", "formula", "figure", "caption", "reference", "other"
]
Confidence = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class ParsedBlock:
    block_id: str
    page: int
    order: int
    type: BlockType
    level: int | None
    text: str
    raw_text: str
    span_map: list[int] = field(repr=False, compare=False)
    bbox: tuple[float, float, float, float] | None
    confidence: Confidence

    def __post_init__(self) -> None:
        if len(self.span_map) != len(self.text) + 1:
            raise ValueError("span_map must contain one raw offset per text boundary")
        if any(offset < 0 or offset > len(self.raw_text) for offset in self.span_map):
            raise ValueError("span_map offsets must be within raw_text")
        if any(
            left > right for left, right in zip(self.span_map[:-1], self.span_map[1:], strict=True)
        ):
            raise ValueError("span_map offsets must be non-decreasing")


@dataclass(frozen=True)
class DocumentGeometry:
    page: int
    page_rotation: int
    cropbox: tuple[float, float, float, float]


@dataclass(frozen=True)
class CitationSpan:
    block_id: str
    raw_span: tuple[int, int]
    page: int
    excerpt: str


@dataclass(frozen=True)
class Reference:
    ref_number: int | None
    raw: str
    title: str | None = None
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    arxiv_id: str | None = None


@dataclass(frozen=True)
class PaperStructure:
    title: str | None
    authors: list[str]
    affiliations: list[str]
    abstract: str | None
    blocks: list[ParsedBlock]
    page_geometries: list[DocumentGeometry]
    confidence: Confidence

    @property
    def toc(self) -> list[dict]:
        return derive_toc(self.blocks)

    @property
    def references(self) -> list[Reference]:
        return derive_refs(self.blocks)

    def to_persistable(self) -> dict[str, object]:
        return {
            "title": self.title,
            "authors": list(self.authors),
            "affiliations": list(self.affiliations),
            "abstract": self.abstract,
            "blocks": [
                {
                    item.name: getattr(block, item.name)
                    for item in fields(block)
                    if item.name != "span_map"
                }
                for block in self.blocks
            ],
            "page_geometries": [
                {
                    "page": geometry.page,
                    "page_rotation": geometry.page_rotation,
                    "cropbox": list(geometry.cropbox),
                }
                for geometry in self.page_geometries
            ],
            "confidence": self.confidence,
        }


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    PARSING = "parsing"
    INDEXING = "indexing"
    INDEXED = "indexed"
    PARTIAL = "partial"
    FAILED = "failed"
    PROCESSING = "processing"


class UploadState(StrEnum):
    UPLOADED = "uploaded"
    PARSING = "parsing"
    DUPLICATE_PENDING = "duplicate_pending"
    INDEXING = "indexing"
    INDEXED = "indexed"
    PARTIAL = "partial"
    FAILED = "failed"
    KEPT_EXISTING = "kept_existing"


class UploadEvent(StrEnum):
    START_PARSING = "start_parsing"
    NO_DUPLICATE = "no_duplicate"
    DUPLICATE_FOUND = "duplicate_found"
    KEEP_EXISTING = "keep_existing"
    OVERWRITE = "overwrite"
    KEEP_BOTH = "keep_both"
    INDEXED = "indexed"
    PARTIAL = "partial"
    FAILED = "failed"


class ConfidenceUse(StrEnum):
    AUTO_CITATION = "auto_citation"
    REQUIRE_QUOTE_VERIFICATION = "require_quote_verification"
    PLAIN_TEXT_FALLBACK = "plain_text_fallback"


class SSEEvent(StrEnum):
    MESSAGE_START = "message_start"
    RETRIEVAL = "retrieval"
    TOKEN = "token"
    CITATIONS = "citations"
    MESSAGE_END = "message_end"
    GUARDRAIL = "guardrail"
    PLAN = "plan"
    TOOL_CALL = "tool_call"


def normalize_with_span_map(raw_text: str) -> tuple[str, list[int]]:
    text_parts: list[str] = []
    span_map: list[int] = []
    pending_whitespace: re.Match[str] | None = None

    for match in re.finditer(r"\s+|\S+", raw_text):
        if match.group().isspace():
            if text_parts:
                pending_whitespace = match
            continue

        if not text_parts:
            span_map.append(match.start())
        elif pending_whitespace is not None:
            text_parts.append(" ")
            span_map.append(pending_whitespace.end())

        text_parts.extend(match.group())
        span_map.extend(range(match.start() + 1, match.end() + 1))
        pending_whitespace = None

    return "".join(text_parts), span_map or [0]


def derive_toc(blocks: list[ParsedBlock]) -> list[dict]:
    titles = (block for block in blocks if block.type == "title")
    return [
        {
            "block_id": block.block_id,
            "page": block.page,
            "order": block.order,
            "level": block.level,
            "title": block.text,
        }
        for block in sorted(titles, key=lambda item: (item.page, item.order, item.block_id))
    ]


_REFERENCE_NUMBER = re.compile(r"^\s*(?:\[(\d+)\]|(\d+)[.)])")
_REFERENCE_YEAR = re.compile(r"\b((?:19|20)\d{2})\b")
_ARXIV_ID = re.compile(
    r"(?:arxiv:\s*)?(\d{4}\.\d{4,5}(?:v\d+)?|[a-z][a-z.-]*/\d{7}(?:v\d+)?)",
    re.IGNORECASE,
)


def derive_refs(blocks: list[ParsedBlock]) -> list[Reference]:
    reference_blocks = (block for block in blocks if block.type == "reference")
    references: list[Reference] = []
    for block in sorted(reference_blocks, key=lambda item: (item.page, item.order, item.block_id)):
        number_match = _REFERENCE_NUMBER.match(block.raw_text)
        year_match = _REFERENCE_YEAR.search(block.raw_text)
        arxiv_match = _ARXIV_ID.search(block.raw_text)
        number = (
            next(
                (int(value) for value in number_match.groups() if value is not None),
                None,
            )
            if number_match
            else None
        )
        references.append(
            Reference(
                ref_number=number,
                raw=block.raw_text,
                year=int(year_match.group(1)) if year_match else None,
                arxiv_id=arxiv_match.group(1) if arxiv_match else None,
            )
        )
    return references


def resolve_reference(ref_number: int | None, references: list[Reference]) -> Reference | None:
    if ref_number is None:
        return None
    matches = [reference for reference in references if reference.ref_number == ref_number]
    return matches[0] if len(matches) == 1 else None


def confidence_use(confidence: Confidence) -> ConfidenceUse:
    return {
        "high": ConfidenceUse.AUTO_CITATION,
        "medium": ConfidenceUse.REQUIRE_QUOTE_VERIFICATION,
        "low": ConfidenceUse.PLAIN_TEXT_FALLBACK,
    }[confidence]


def validate_sse_event_order(events: Sequence[SSEEvent]) -> None:
    if any(not isinstance(event, SSEEvent) for event in events):
        raise ValueError("unknown SSE event")
    if SSEEvent.GUARDRAIL in events and SSEEvent.TOKEN in events:
        raise ValueError("guardrail refusal must not emit token")
    if not events or events[0] != SSEEvent.MESSAGE_START or events[-1] != SSEEvent.MESSAGE_END:
        raise ValueError("message_start must be first and message_end must be last")

    for required in (
        SSEEvent.MESSAGE_START,
        SSEEvent.RETRIEVAL,
        SSEEvent.CITATIONS,
        SSEEvent.MESSAGE_END,
    ):
        if events.count(required) != 1:
            raise ValueError(f"{required.value} must occur exactly once")

    retrieval_index = events.index(SSEEvent.RETRIEVAL)
    citations_index = events.index(SSEEvent.CITATIONS)
    token_indices = [index for index, event in enumerate(events) if event == SSEEvent.TOKEN]
    if retrieval_index >= citations_index or any(
        not retrieval_index < index < citations_index for index in token_indices
    ):
        raise ValueError("retrieval, token, and citations events are out of order")


def transition_upload_state(
    current: UploadState,
    event: UploadEvent,
    *,
    identical_sha256: bool | None = None,
) -> UploadState:
    if current == UploadState.UPLOADED and event == UploadEvent.START_PARSING:
        return UploadState.PARSING
    if current == UploadState.PARSING:
        if event == UploadEvent.NO_DUPLICATE:
            return UploadState.INDEXING
        if event == UploadEvent.DUPLICATE_FOUND:
            return UploadState.DUPLICATE_PENDING
        if event == UploadEvent.FAILED:
            return UploadState.FAILED
    if current == UploadState.DUPLICATE_PENDING:
        if event == UploadEvent.KEEP_EXISTING:
            return UploadState.KEPT_EXISTING
        if event in {UploadEvent.OVERWRITE, UploadEvent.KEEP_BOTH}:
            if identical_sha256 is None:
                raise ValueError("SHA-256 comparison is required for overwrite or keep_both")
            if identical_sha256:
                raise ValueError("identical SHA-256 duplicates only allow keep_existing")
            return UploadState.INDEXING
    if current == UploadState.INDEXING:
        if event == UploadEvent.INDEXED:
            return UploadState.INDEXED
        if event == UploadEvent.PARTIAL:
            return UploadState.PARTIAL
        if event == UploadEvent.FAILED:
            return UploadState.FAILED
    if current == UploadState.PARTIAL:
        if event == UploadEvent.INDEXED:
            return UploadState.INDEXED
        if event == UploadEvent.FAILED:
            return UploadState.FAILED
    raise ValueError(f"invalid upload transition: {current.value} -> {event.value}")
