import json
from dataclasses import FrozenInstanceError, fields

import pytest

from rag_api.domain.contracts import (
    CitationSpan,
    ConfidenceUse,
    DocumentGeometry,
    DocumentStatus,
    PaperStructure,
    ParsedBlock,
    Reference,
    SSEEvent,
    confidence_use,
    derive_refs,
    derive_toc,
    normalize_with_span_map,
    resolve_reference,
    validate_sse_event_order,
)


def make_block(
    *,
    block_id: str,
    page: int,
    order: int,
    block_type: str,
    raw_text: str,
    level: int | None = None,
) -> ParsedBlock:
    text, span_map = normalize_with_span_map(raw_text)
    return ParsedBlock(
        block_id=block_id,
        page=page,
        order=order,
        type=block_type,  # type: ignore[arg-type]
        level=level,
        text=text,
        raw_text=raw_text,
        span_map=span_map,
        bbox=None,
        confidence="high",
    )


def test_parsed_block_shape_and_span_map_contract() -> None:
    raw_text = " \tFirst  \r\n  paragraph. \t"
    text, span_map = normalize_with_span_map(raw_text)
    block = ParsedBlock(
        block_id="block-1",
        page=1,
        order=0,
        type="paragraph",
        level=None,
        text=text,
        raw_text=raw_text,
        span_map=span_map,
        bbox=(1.0, 2.0, 3.0, 4.0),
        confidence="medium",
    )

    assert text == "First paragraph."
    assert len(span_map) == len(text) + 1
    assert span_map == sorted(span_map)
    assert "span_map" not in repr(block)
    span_map_field = next(item for item in fields(ParsedBlock) if item.name == "span_map")
    assert span_map_field.repr is False
    assert span_map_field.compare is False
    with pytest.raises(FrozenInstanceError):
        block.text = "changed"  # type: ignore[misc]

    assert DocumentStatus.PROCESSING.value == "processing"
    assert DocumentStatus.INDEXED.value == "indexed"
    assert [confidence_use(value) for value in ("high", "medium", "low")] == [
        ConfidenceUse.AUTO_CITATION,
        ConfidenceUse.REQUIRE_QUOTE_VERIFICATION,
        ConfidenceUse.PLAIN_TEXT_FALLBACK,
    ]
    validate_sse_event_order(
        [
            SSEEvent.MESSAGE_START,
            SSEEvent.PLAN,
            SSEEvent.RETRIEVAL,
            SSEEvent.TOOL_CALL,
            SSEEvent.TOKEN,
            SSEEvent.CITATIONS,
            SSEEvent.MESSAGE_END,
        ]
    )
    with pytest.raises(ValueError, match="out of order"):
        validate_sse_event_order(
            [
                SSEEvent.MESSAGE_START,
                SSEEvent.TOKEN,
                SSEEvent.RETRIEVAL,
                SSEEvent.CITATIONS,
                SSEEvent.MESSAGE_END,
            ]
        )
    for invalid_events in (
        [SSEEvent.MESSAGE_START, SSEEvent.CITATIONS, SSEEvent.MESSAGE_END],
        [
            SSEEvent.MESSAGE_START,
            SSEEvent.RETRIEVAL,
            SSEEvent.CITATIONS,
            SSEEvent.CITATIONS,
            SSEEvent.MESSAGE_END,
        ],
        [
            SSEEvent.MESSAGE_START,
            SSEEvent.RETRIEVAL,
            SSEEvent.CITATIONS,
            SSEEvent.TOKEN,
            SSEEvent.MESSAGE_END,
        ],
        [
            SSEEvent.MESSAGE_START,
            SSEEvent.RETRIEVAL,
            "unknown",  # type: ignore[list-item]
            SSEEvent.CITATIONS,
            SSEEvent.MESSAGE_END,
        ],
    ):
        with pytest.raises(ValueError):
            validate_sse_event_order(invalid_events)
    with pytest.raises(ValueError, match="guardrail refusal must not emit token"):
        validate_sse_event_order(
            [
                SSEEvent.MESSAGE_START,
                SSEEvent.RETRIEVAL,
                SSEEvent.GUARDRAIL,
                SSEEvent.CITATIONS,
                SSEEvent.TOKEN,
                SSEEvent.MESSAGE_END,
            ]
        )


def test_citation_span_round_trips_normalized_text_to_raw_excerpt() -> None:
    raw_text = "\tAlpha \r\n  beta and gamma.  "
    text, span_map = normalize_with_span_map(raw_text)
    start = text.index("beta")
    end = start + len("beta and gamma.")
    raw_start, raw_end = span_map[start], span_map[end]
    citation = CitationSpan(
        block_id="block-1",
        raw_span=(raw_start, raw_end),
        page=3,
        excerpt=raw_text[raw_start:raw_end],
    )

    assert citation.excerpt == raw_text[raw_start:raw_end]
    normalized_excerpt, _ = normalize_with_span_map(citation.excerpt)
    assert normalized_excerpt == text[start:end]


def test_toc_and_references_are_deterministic_block_projections() -> None:
    blocks = [
        make_block(
            block_id="ref-2",
            page=2,
            order=1,
            block_type="reference",
            raw_text="Unnumbered source",
        ),
        make_block(
            block_id="title-2",
            page=2,
            order=0,
            block_type="title",
            raw_text="Methods",
            level=2,
        ),
        make_block(
            block_id="ref-1",
            page=1,
            order=2,
            block_type="reference",
            raw_text="[4] A paper (2021). arXiv:2101.12345",
        ),
        make_block(
            block_id="title-1",
            page=1,
            order=0,
            block_type="title",
            raw_text="Introduction",
            level=1,
        ),
    ]
    structure = PaperStructure(
        title="Example",
        authors=["A. Author"],
        affiliations=["Example University"],
        abstract=None,
        blocks=blocks,
        page_geometries=[DocumentGeometry(1, 90, (0.0, 0.0, 200.0, 100.0))],
        confidence="high",
    )

    assert structure.toc == derive_toc(blocks)
    assert [item["block_id"] for item in structure.toc] == ["title-1", "title-2"]
    assert structure.toc[0]["title"] == "Introduction"
    assert structure.references == derive_refs(blocks)
    assert [(item.ref_number, item.year, item.arxiv_id) for item in structure.references] == [
        (4, 2021, "2101.12345"),
        (None, None, None),
    ]
    assert structure.references[1].raw == "Unnumbered source"
    assert resolve_reference(4, structure.references) == structure.references[0]
    assert resolve_reference(99, structure.references) is None
    assert resolve_reference(None, structure.references) is None
    assert (
        resolve_reference(
            4,
            [*structure.references, Reference(ref_number=4, raw="Another reference")],
        )
        is None
    )


def test_persistable_projection_keeps_geometry_but_omits_derived_and_memory_fields() -> None:
    block = make_block(
        block_id="block-1",
        page=1,
        order=0,
        block_type="paragraph",
        raw_text="A  paragraph.",
    )
    structure = PaperStructure(
        title="Example",
        authors=[],
        affiliations=[],
        abstract=None,
        blocks=[block],
        page_geometries=[DocumentGeometry(1, 0, (0.0, 0.0, 612.0, 792.0))],
        confidence="low",
    )

    payload = structure.to_persistable()
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    assert "span_map" not in payload["blocks"][0]
    assert "toc" not in payload
    assert "references" not in payload
    assert payload["page_geometries"] == [
        {"page": 1, "page_rotation": 0, "cropbox": [0.0, 0.0, 612.0, 792.0]}
    ]
    assert "span_map" not in encoded
