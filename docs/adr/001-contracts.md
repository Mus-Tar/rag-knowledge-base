# ADR 001: Parsed Document Contracts

- Status: Accepted
- Scope: T-0.2 contract freeze

## Decision

`PaperStructure.blocks` is the sole source of parsed document content. A block carries
its stable identity, document order, normalized and raw text, page, optional geometry,
and confidence. The table of contents and reference list are deterministic projections
of blocks; they are not stored as parallel facts that could drift out of sync.

Text block bounding boxes use PyMuPDF's unrotated page coordinates. `page.rect` is not
the coordinate baseline. Page rotation and cropbox are retained separately in
`PaperStructure.page_geometries` so a later presentation layer can transform geometry
without changing stored parser coordinates.

`ParsedBlock.span_map` maps each boundary in normalized `text` to a character offset in
`raw_text`, so its length is `len(text) + 1`. A citation match over `[start, end)` maps
to `raw_text[span_map[start]:span_map[end]]`; the citation excerpt is that raw slice,
not the matched quote. The map is runtime-only. It can be regenerated from `raw_text`
using the frozen whitespace-normalization rule, while persistent blocks retain both
text forms for verification.

Reference projections preserve the raw reference and recognize an explicit leading
number, four-digit year, and arXiv identifier when present. They do not infer authors
or titles from ambiguous citation text; those fields remain unknown until a parser
provides them. `resolve_reference` returns `None` for an absent, out-of-range, or
ambiguous reference number; `None` is the contract's unmapped result, not a
list-position guess.

Confidence use is explicit: high is eligible for citation, medium is a stronger
"pending confirmation" state and must pass quote verification, and low maps to
plain-text fallback. This is a policy contract, not a calibration claim; calibration
requires a separately labeled sample set.

`DocumentStatus` describes document lifecycle. `UploadState` describes an upload job,
including `duplicate_pending`; the legacy `processing` value remains readable without
guessing whether it meant parsing or indexing. Identical SHA-256 duplicates may only
resolve to `keep_existing`. `keep_both` is reserved for similar documents with
different SHA-256 values.

The SSE contract requires `message_start`, then `retrieval`, zero or more `token`
events, `citations`, and `message_end` in that order. `plan`, `tool_call`, and
`guardrail` may appear between the boundary events; their relative order is not
constrained here. A guardrail refusal must not emit any `token` event. The SSE `id:`
field remains P1.

## Consequences

Persistence includes page geometry and block source text, but excludes `span_map`,
`toc`, and `references`. Citation offsets can be rebuilt and checked against raw text.
This ADR does not change database migrations, upload endpoints, or frontend coordinate
conversion or current SSE producers. The 30-sample confidence calibration, 541-page
size check, and upload HTTP/database/vector integration paths remain follow-up work.

Frozen dataclasses do not make contained lists immutable. Consumers must treat list
fields as read-only; changing them to tuples is deferred.

## TODO

- Add negative `span_map` tests for incorrect length, out-of-range offsets, and
  decreasing offsets.
- Revisit tuple-backed fields or enforce the documented read-only convention for
  lists inside frozen dataclasses.
