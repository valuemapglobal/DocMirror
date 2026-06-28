#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Report clean-manifest quarantine modules and fail on expired reviews."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.code_hygiene.clean_manifest import load_clean_manifest  # noqa: E402


def _parse_date(raw: str) -> date:
    return datetime.strptime(raw, "%Y-%m-%d").date()


def build_report(*, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    manifest = load_clean_manifest()
    items = []
    for item in manifest.data.get("quarantine_modules") or []:
        review_by = _parse_date(str(item["review_by"]))
        days_remaining = (review_by - today).days
        status = "overdue" if days_remaining < 0 else "due_soon" if days_remaining <= 14 else "scheduled"
        items.append(
            {
                "module": item["module"],
                "owner": item.get("owner", ""),
                "review_by": str(review_by),
                "days_remaining": days_remaining,
                "status": status,
                "reason": item.get("reason", ""),
                "exit_criteria": item.get("exit_criteria", ""),
            }
        )
    items.sort(key=lambda x: (x["days_remaining"], x["owner"], x["module"]))
    counts = Counter(item["status"] for item in items)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "today": str(today),
        "total": len(items),
        "counts": dict(counts),
        "items": items,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary-json", type=Path, help="Write machine-readable report JSON")
    parser.add_argument("--fail-overdue", action="store_true", help="Exit non-zero when any item is overdue")
    parser.add_argument("--today", help="Override current date for tests, YYYY-MM-DD")
    args = parser.parse_args()

    today = _parse_date(args.today) if args.today else None
    report = build_report(today=today)

    if args.summary_json:
        args.summary_json.parent.mkdir(parents=True, exist_ok=True)
        args.summary_json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    counts = report["counts"]
    print(
        "Clean quarantine report: "
        f"total={report['total']} "
        f"scheduled={counts.get('scheduled', 0)} "
        f"due_soon={counts.get('due_soon', 0)} "
        f"overdue={counts.get('overdue', 0)}"
    )
    for item in report["items"]:
        if item["status"] in {"overdue", "due_soon"}:
            print(
                f"  - [{item['status']}] {item['module']} "
                f"owner={item['owner']} review_by={item['review_by']} "
                f"days={item['days_remaining']}"
            )

    if args.fail_overdue and counts.get("overdue", 0):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

