"""T-0.5 acceptance entry point.

Only asset, corpus and manifest validation are implemented here. The
end-to-end flow depends on T-1.1 (async upload) and T-2.1 (duplicate
confirm), so this script exits 2 with an explicit message instead of
pretending that the E2E passed.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from check_official import (
    DEFAULT_DIR,
    MIN_CORPUS_PAPERS,
    check_manifest,
    corpus_count,
    print_report,
    validate,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Official test-asset acceptance")
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR, help="directory with the PDFs")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--check-assets", action="store_true", help="only validate the local assets"
    )
    args = parser.parse_args()

    rows = validate(args.dir)
    print_report(rows)
    failed = [row for row in rows if row["status"] != "ok"]
    other = corpus_count(args.dir)
    corpus_ok = other >= MIN_CORPUS_PAPERS
    manifest_ok, manifest_message = check_manifest(args.dir)
    print(
        f"corpus: {other} other papers (min {MIN_CORPUS_PAPERS}) -> {'ok' if corpus_ok else 'FAIL'}"
    )
    print(f"manifest: {manifest_message} -> {'ok' if manifest_ok else 'FAIL'}")

    if failed or not corpus_ok or not manifest_ok:
        print("asset / corpus / manifest checks failed; fix them before running E2E.")
        return 1
    if args.check_assets:
        print("Assets, corpus and manifest OK. E2E is still pending T-1.1/T-2.1.")
        return 0

    print(f"Assets OK; E2E is not implemented yet (API: {args.api_url}).")
    print("Implement upload / duplicate / confirm / OCR / 541-page checks in T-1.1/T-2.1.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
