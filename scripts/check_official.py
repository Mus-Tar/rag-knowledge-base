"""Validate the local copy of the official PDF test assets.

The PDFs live in ``official_pdf/pdf/`` and are intentionally gitignored:
they are large and may be copyrighted. This script is the supported way to
prove that the local copy matches the official test set before running the
online acceptance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import fitz

DEFAULT_DIR = Path("official_pdf/pdf")
MANIFEST_PATH = Path("tests/fixtures/official/manifest.json")
MIN_CORPUS_PAPERS = 35

EXPECTED: dict[str, dict[str, Any]] = {
    "1706.03762v1.pdf": {
        "role": "dedup_v1",
        "bytes": 2_128_686,
        "pages": 15,
        "sha256": "0a9bff1be3575cf9fe26a4a3d3a9175bc791ecec90de8b9deba4cff75d2b9476",
    },
    "1706.03762v7.pdf": {
        "role": "dedup_v7",
        "bytes": 2_215_244,
        "pages": 15,
        "sha256": "bdfaa68d8984f0dc02beaca527b76f207d99b666d31d1da728ee0728182df697",
    },
    "1706.03762v1_img.pdf": {
        "role": "ocr_scan",
        "bytes": 4_672_118,
        "pages": 15,
        "sha256": "64094fe169dd4ff454f579e9f197298df1c118c24b71b1f1ca8bb218c9e4801d",
    },
    "UnderstandingDeepLearning_02_09_26_C.pdf": {
        "role": "long_book",
        "bytes": 22_344_992,
        "pages": 541,
        "sha256": "f8237d393163900fa8e43210e680a3f987b45ccac7750b372e156fae3df0bf32",
    },
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def page_count(path: Path) -> int:
    document = fitz.open(path)
    try:
        return document.page_count
    finally:
        document.close()


def corpus_count(directory: Path) -> int:
    return sum(1 for path in directory.glob("*.pdf") if path.name not in EXPECTED)


def validate(directory: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, expected in EXPECTED.items():
        path = directory / name
        row: dict[str, Any] = {
            "name": name,
            "role": expected["role"],
            "path": path,
            "expected": expected,
            "actual": None,
            "problems": [],
            "status": "missing",
        }
        if path.is_file():
            actual: dict[str, Any] = {
                "bytes": path.stat().st_size,
                "pages": None,
                "sha256": sha256_file(path),
            }
            try:
                actual["pages"] = page_count(path)
            except Exception as exc:  # corrupted/unreadable PDF must fail cleanly
                row.update(actual=actual, status="unreadable", error=str(exc))
                rows.append(row)
                continue
            problems = [key for key in ("bytes", "pages", "sha256") if actual[key] != expected[key]]
            row.update(
                actual=actual,
                problems=problems,
                status="ok" if not problems else "mismatch",
            )
        rows.append(row)
    return rows


def print_report(rows: list[dict[str, Any]]) -> None:
    print(f"{'file':46} {'role':12} {'pages':>5} {'sha256':10} status")
    for row in rows:
        actual = row["actual"] or {}
        pages = actual.get("pages", "-")
        digest = str(actual.get("sha256", "-"))[:10]
        print(f"{row['name']:46} {row['role']:12} {pages!s:>5} {digest:10} {row['status']}")
        if row["status"] == "mismatch":
            for key in row["problems"]:
                print(f"  {key}: expected {row['expected'][key]!r}, got {actual[key]!r}")
        if row["status"] == "unreadable":
            print(f"  unreadable: {row['error']}")


def check_manifest(directory: Path) -> tuple[bool, str]:
    if not MANIFEST_PATH.is_file():
        return False, f"manifest missing: {MANIFEST_PATH}"
    try:
        payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"manifest unreadable: {exc}"
    files = payload.get("files")
    if not isinstance(files, list):
        return False, "manifest has no files list"
    by_name = {item.get("name"): item for item in files if isinstance(item, dict)}
    for name, expected in EXPECTED.items():
        item = by_name.get(name)
        if not isinstance(item, dict):
            return False, f"manifest missing {name}"
        for key in ("role", "bytes", "pages", "sha256"):
            if item.get(key) != expected[key]:
                return False, f"manifest mismatch {name}.{key}"
    actual_other = corpus_count(directory)
    if payload.get("other_pdf_count") != actual_other:
        return False, (
            f"manifest other_pdf_count={payload.get('other_pdf_count')} "
            f"but directory has {actual_other}"
        )
    return True, "manifest matches EXPECTED and corpus count"


def write_manifest(directory: Path) -> None:
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source_dir": directory.as_posix(),
        "official": True,
        "files": [
            {
                "name": name,
                "role": expected["role"],
                "bytes": expected["bytes"],
                "pages": expected["pages"],
                "sha256": expected["sha256"],
            }
            for name, expected in EXPECTED.items()
        ],
        "other_pdf_count": corpus_count(directory),
        "note": "PDFs are local-only and gitignored; this manifest is the committed evidence.",
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"manifest written: {MANIFEST_PATH}")


def inventory(directory: Path) -> None:
    items = [
        {
            "name": path.name,
            "bytes": path.stat().st_size,
            "pages": page_count(path),
            "sha256": sha256_file(path),
        }
        for path in sorted(directory.glob("*.pdf"))
    ]
    print(json.dumps(items, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the official PDF test assets")
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR, help="directory with the PDFs")
    parser.add_argument(
        "--write-manifest", action="store_true", help="write the committed manifest"
    )
    parser.add_argument(
        "--inventory", action="store_true", help="list every PDF with pages and hash"
    )
    args = parser.parse_args()

    if not args.dir.is_dir():
        print(f"directory not found: {args.dir}")
        return 1
    if args.inventory:
        if not any(args.dir.glob("*.pdf")):
            print(f"no PDFs found in {args.dir}")
            return 1
        inventory(args.dir)
        return 0

    rows = validate(args.dir)
    print_report(rows)
    assets_ok = all(row["status"] == "ok" for row in rows)
    if args.write_manifest and assets_ok:
        write_manifest(args.dir)

    other = corpus_count(args.dir)
    corpus_ok = other >= MIN_CORPUS_PAPERS
    print(
        f"corpus: {other} other papers (min {MIN_CORPUS_PAPERS}) -> {'ok' if corpus_ok else 'FAIL'}"
    )
    manifest_ok, manifest_message = check_manifest(args.dir)
    print(f"manifest: {manifest_message} -> {'ok' if manifest_ok else 'FAIL'}")
    return 0 if assets_ok and corpus_ok and manifest_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
