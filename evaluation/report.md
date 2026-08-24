# RAG Validation Report

## Run Metadata

| Field | Value |
| --- | --- |
| Run ID | `1850e225c4c14accaf9810f550387e05` |
| Date | 2026-07-25 (UTC) |
| Dataset | `rag-resume-evidence-v1` |
| Dataset SHA-256 | `6bae4ebf532c8ed437b272efcf69cea357b2e89fafa4a143d5b340f21684bb70` |
| Sources / questions | 10 / 20 |
| Model provider | `fake` |
| Retrieval baseline | 384-dimensional normalized lexical feature hash |
| Runtime | Python 3.12.0, Windows 11, Docker Compose API/Web stack |

## Retrieval and Answer Metrics

| Metric | Result |
| --- | ---: |
| Hit@1 | 85.00% |
| Hit@4 | 100.00% |
| MRR@4 | 0.9167 |
| Fixed answer-term pass rate | 85.00% (17/20) |

The three non-passing questions were the structured citation field question, the two Streamlit
widget names question, and the deduplication ordering question. The source was still retrieved for
all three; two were ranked second and one third. The failures indicate lexical phrase/term handling
limits in the offline baseline, not missing source data.

## Latency (milliseconds)

| Operation | Samples | P50 | P95 | Max |
| --- | ---: | ---: | ---: | ---: |
| PDF upload and indexing | 10 | 67.21 | 76.20 | 76.20 |
| First streamed token | 20 | 21.71 | 36.04 | 37.53 |
| Complete streamed answer | 20 | 119.91 | 135.08 | 139.23 |
| Health probe | 30 | 8.27 | 36.85 | 41.57 |

These are local single-user measurements on the fake provider with one-page generated PDFs. They
are baseline engineering measurements, not production capacity or concurrency claims.

## Reproduction

```powershell
docker compose up --detach --build --wait
uv run python evaluation/run_evaluation.py --output evaluation/results/run-YYYY-MM-DD.json
```

The evaluator requires an empty document collection, uses only the public HTTP/SSE interfaces, and
removes its generated documents in a `finally` block.
