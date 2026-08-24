# Evaluation

This directory contains a deterministic validation set for the local knowledge base.

## Dataset

`qa_dataset.json` contains 10 generated one-page PDF source documents and 20 questions. Each
question has one expected source filename and a small set of answer terms. The dataset is versioned
and its SHA-256 is included in every result file.

## Run

Run against a fresh Compose volume so no unrelated documents affect retrieval:

```powershell
docker compose up --detach --build --wait
uv run python evaluation/run_evaluation.py --output evaluation/results/run-YYYY-MM-DD.json
```

The evaluator checks API and Streamlit health, uploads every source PDF, sends every question over
the public SSE endpoint, records source ranks and latency, then deletes the generated documents.
It writes Hit@1, Hit@4, MRR@4, deterministic answer-term pass rate, upload latency, first-token
latency, and total-answer latency.

The answer-term metric validates the fake-provider pipeline and citation plumbing. It is not an
LLM answer-quality score. The current vector baseline is a deterministic 384-dimensional lexical
feature hash, so semantic embedding quality is intentionally outside this result.

## Latest Run

See [run-2026-07-25.json](results/run-2026-07-25.json) and the summarized [report](report.md).
