import argparse
import hashlib
import json
import math
import os
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

import fitz
import httpx

DEFAULT_DATASET = Path(__file__).with_name("qa_dataset.json")
DEFAULT_OUTPUT = Path(__file__).with_name("results") / "latest.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the running RAG application")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--web-url", default="http://127.0.0.1:8501")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    result = evaluate(
        api_url=args.api_url.rstrip("/"),
        web_url=args.web_url.rstrip("/"),
        dataset_path=args.dataset,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"Full result: {args.output.resolve()}")


def evaluate(*, api_url: str, web_url: str, dataset_path: Path) -> dict[str, Any]:
    dataset_bytes = dataset_path.read_bytes()
    dataset = json.loads(dataset_bytes)
    started_at = datetime.now(UTC)
    run_id = uuid4().hex
    uploaded_ids: list[str] = []
    upload_latencies: list[float] = []
    query_results: list[dict[str, Any]] = []

    with httpx.Client(timeout=60) as client:
        _assert_stack_ready(client, api_url, web_url)
        existing = client.get(f"{api_url}/api/documents").json()["documents"]
        if existing:
            raise RuntimeError(
                "Evaluation requires an empty knowledge base; use a fresh Compose volume"
            )

        try:
            for document in dataset["documents"]:
                content = _make_pdf(document["title"], document["body"])
                started = perf_counter()
                response = client.post(
                    f"{api_url}/api/documents",
                    files={
                        "file": (
                            document["filename"],
                            content,
                            "application/pdf",
                        )
                    },
                )
                upload_latencies.append(_elapsed_ms(started))
                response.raise_for_status()
                uploaded_ids.append(response.json()["id"])

            conversation = client.post(
                f"{api_url}/api/conversations",
                json={"title": f"Evaluation {run_id[:8]}"},
            )
            conversation.raise_for_status()
            conversation_id = conversation.json()["id"]

            for item in dataset["questions"]:
                answer, citations, first_token_ms, total_ms = _ask(
                    client,
                    api_url,
                    conversation_id,
                    item["question"],
                )
                filenames = [citation["filename"] for citation in citations]
                try:
                    rank = filenames.index(item["relevant_filename"]) + 1
                except ValueError:
                    rank = None
                expected_terms = item["expected_answer_terms"]
                normalized_answer = answer.casefold()
                terms_passed = [
                    term for term in expected_terms if term.casefold() in normalized_answer
                ]
                query_results.append(
                    {
                        "id": item["id"],
                        "question": item["question"],
                        "relevant_filename": item["relevant_filename"],
                        "retrieved_filenames": filenames,
                        "rank": rank,
                        "answer_keyword_pass": len(terms_passed) == len(expected_terms),
                        "expected_terms": expected_terms,
                        "matched_terms": terms_passed,
                        "first_token_ms": first_token_ms,
                        "total_ms": total_ms,
                    }
                )

            health_latencies = []
            for _ in range(30):
                started = perf_counter()
                response = client.get(f"{api_url}/health")
                response.raise_for_status()
                health_latencies.append(_elapsed_ms(started))
        finally:
            for document_id in uploaded_ids:
                client.delete(f"{api_url}/api/documents/{document_id}").raise_for_status()

    retrieval = _retrieval_metrics(query_results)
    qa_passes = sum(result["answer_keyword_pass"] for result in query_results)
    first_token_latencies = [result["first_token_ms"] for result in query_results]
    total_latencies = [result["total_ms"] for result in query_results]
    performance = {
        "upload_ms": _latency_summary(upload_latencies),
        "health_ms": _latency_summary(health_latencies),
        "first_token_ms": _latency_summary(first_token_latencies),
        "answer_total_ms": _latency_summary(total_latencies),
    }
    qa_keyword_pass_rate = round(qa_passes / len(query_results), 4)
    llm_provider = os.environ.get("RAG_LLM_PROVIDER", "fake")
    llm_model = os.environ.get("RAG_LLM_MODEL", "qwen3:4b")
    embedding_provider = os.environ.get("RAG_EMBEDDING_PROVIDER", "lexical")
    embedding_model = os.environ.get("RAG_EMBEDDING_MODEL", "bge-m3")
    embedding_dimensions = int(os.environ.get("RAG_EMBEDDING_DIMENSIONS", "384"))
    raw_index_version = f"{embedding_provider}-{embedding_model}-{embedding_dimensions}"
    index_version = "".join(
        character if character.isalnum() else "-" for character in raw_index_version
    ).strip("-")

    return {
        "schema_version": 1,
        "run_id": run_id,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "api_url": api_url,
            "web_url": web_url,
            "llm_provider": llm_provider,
            "llm_model": llm_model,
            "embedding_provider": embedding_provider,
            "embedding_model": embedding_model,
            "embedding_dimensions": embedding_dimensions,
            "index_version": index_version,
            "model_provider": llm_provider,
            "retrieval_vector": (
                f"{embedding_dimensions}-dimensional {embedding_provider} embedding "
                f"({embedding_model})"
            ),
        },
        "dataset": {
            "name": dataset["name"],
            "schema_version": dataset["schema_version"],
            "sha256": hashlib.sha256(dataset_bytes).hexdigest(),
            "document_count": len(dataset["documents"]),
            "question_count": len(dataset["questions"]),
        },
        "summary": {
            **retrieval,
            "qa_keyword_pass_rate": qa_keyword_pass_rate,
            "question_count": len(query_results),
            "upload_p95_ms": performance["upload_ms"]["p95"],
            "first_token_p95_ms": performance["first_token_ms"]["p95"],
            "answer_total_p95_ms": performance["answer_total_ms"]["p95"],
        },
        "retrieval": retrieval,
        "qa": {
            "keyword_passes": qa_passes,
            "keyword_pass_rate": qa_keyword_pass_rate,
            "scope": "Deterministic fake-provider pipeline validation, not LLM answer quality",
        },
        "performance": performance,
        "queries": query_results,
    }


def _assert_stack_ready(client: httpx.Client, api_url: str, web_url: str) -> None:
    api_health = client.get(f"{api_url}/health")
    web_health = client.get(f"{web_url}/_stcore/health")
    api_health.raise_for_status()
    web_health.raise_for_status()
    if api_health.json().get("status") != "ok" or web_health.text != "ok":
        raise RuntimeError("The API and Streamlit services must both be healthy")


def _make_pdf(title: str, body: str) -> bytes:
    document = fitz.open()
    try:
        page = document.new_page()
        page.insert_textbox(
            fitz.Rect(72, 72, 540, 720),
            f"{title}\n\n{body}",
            fontsize=11,
        )
        return document.tobytes()
    finally:
        document.close()


def _ask(
    client: httpx.Client,
    api_url: str,
    conversation_id: str,
    question: str,
) -> tuple[str, list[dict[str, Any]], float, float]:
    started = perf_counter()
    first_token_ms: float | None = None
    answer_parts: list[str] = []
    citations: list[dict[str, Any]] = []
    event_name = "message"
    data_lines: list[str] = []

    with client.stream(
        "POST",
        f"{api_url}/api/conversations/{conversation_id}/messages:stream",
        json={"question": question},
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line:
                if data_lines:
                    data = json.loads("\n".join(data_lines))
                    if event_name == "token":
                        if first_token_ms is None:
                            first_token_ms = _elapsed_ms(started)
                        answer_parts.append(str(data.get("text", "")))
                    elif event_name == "citations":
                        citations = data.get("items", [])
                    data_lines = []
                continue
            if line.startswith("event: "):
                event_name = line[7:]
            elif line.startswith("data: "):
                data_lines.append(line[6:])

    return (
        "".join(answer_parts),
        citations,
        first_token_ms if first_token_ms is not None else _elapsed_ms(started),
        _elapsed_ms(started),
    )


def _retrieval_metrics(results: list[dict[str, Any]]) -> dict[str, float]:
    count = len(results)
    return {
        "hit_at_1": round(sum(result["rank"] == 1 for result in results) / count, 4),
        "hit_at_4": round(
            sum(result["rank"] is not None and result["rank"] <= 4 for result in results) / count,
            4,
        ),
        "mrr_at_4": round(
            sum(
                1 / result["rank"]
                for result in results
                if result["rank"] is not None and result["rank"] <= 4
            )
            / count,
            4,
        ),
    }


def _latency_summary(values: list[float]) -> dict[str, float]:
    return {
        "min": round(min(values), 2),
        "p50": _percentile(values, 0.50),
        "p95": _percentile(values, 0.95),
        "max": round(max(values), 2),
        "mean": round(sum(values) / len(values), 2),
        "samples": len(values),
    }


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return round(ordered[index], 2)


def _elapsed_ms(started: float) -> float:
    return round((perf_counter() - started) * 1000, 2)


if __name__ == "__main__":
    try:
        main()
    except (httpx.HTTPError, RuntimeError, ValueError, KeyError) as exc:
        print(f"Evaluation failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
