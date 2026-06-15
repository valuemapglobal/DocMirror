#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
"""Benchmark bank_statement community extract across fixture PDFs."""

from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from docmirror.core.entry.factory import PerceiveOptions, perceive_document
from docmirror.plugins.bank_statement.context import build_style_context
from docmirror.plugins.bank_statement.style_detector import BankStyleDetector
from docmirror.plugins.bank_statement.style_registry import BankStyleParserRegistry
from docmirror.plugins.bank_statement.community_plugin import BankStatementCommunityPlugin
from docmirror.plugins.runner import run_plugin_extract_sync

FIXTURE_DIR = ROOT / "tests" / "fixtures" / "bank_statement"


def should_skip(path: Path) -> bool:
    name = path.name
    if "_cleaned" in name:
        return True
    if re.search(r"_\d+_\d+", name):
        return True
    if re.search(r"_[0-9]{1,2}\.pdf$", name):
        return True
    return False


def completeness(records: list[dict]) -> float:
    if not records:
        return 0.0
    fields = ("date", "amount", "balance")
    scores = []
    for rec in records:
        norm = rec.get("normalized") or {}
        scores.append(sum(1 for f in fields if norm.get(f) not in (None, "", 0)) / len(fields))
    return sum(scores) / len(scores)


async def bench_one(pdf: Path) -> dict:
    t0 = time.time()
    row: dict = {"file": pdf.name, "ok": False}
    try:
        result = await perceive_document(pdf, PerceiveOptions(enhance_mode="standard"))
        mirror = result.mirror
        elapsed_perceive = time.time() - t0

        out = run_plugin_extract_sync(
            mirror,
            edition="community",
            full_text=mirror.full_text,
            file_path=str(pdf),
        )
        records = (out or {}).get("data", {}).get("records") or []
        props = (out or {}).get("document", {}).get("properties") or {}
        meta = (out or {}).get("metadata") or {}
        style_id = props.get("style_id") or meta.get("style_id")

        ctx = build_style_context(mirror, mirror.full_text or "")
        detection = BankStyleDetector().detect(ctx)
        plugin = BankStatementCommunityPlugin()
        direct_records, _ = BankStyleParserRegistry().run(detection, ctx, plugin)

        row.update({
            "ok": True,
            "pages": ctx.page_count,
            "tables": len(ctx.tables),
            "style_id": style_id,
            "detected_style": detection.primary_style,
            "confidence": round(detection.confidence, 3),
            "records_cli": len(records),
            "records_direct": len(direct_records),
            "completeness": round(completeness(direct_records), 3),
            "extraction_method": getattr(
                getattr(ctx.parse_result, "parser_info", None),
                "extraction_method",
                None,
            ),
            "perceive_s": round(elapsed_perceive, 1),
            "total_s": round(time.time() - t0, 1),
        })
        if len(direct_records) == 0:
            row["issue"] = "zero_records"
        elif row["completeness"] < 0.5:
            row["issue"] = "low_completeness"
    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"
        row["total_s"] = round(time.time() - t0, 1)
    return row


async def main() -> int:
    pdfs = sorted(p for p in FIXTURE_DIR.glob("*.pdf") if not should_skip(p))
    print(f"Benchmarking {len(pdfs)} PDFs (skipped duplicates/cleaned)...", flush=True)
    results: list[dict] = []
    for i, pdf in enumerate(pdfs, 1):
        print(f"[{i}/{len(pdfs)}] {pdf.name}...", flush=True)
        results.append(await bench_one(pdf))

    out_path = ROOT / "tests" / "fixtures" / "bank_statement" / "bench_report.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    issues = [r for r in results if r.get("issue") or r.get("error")]
    zero = [r for r in results if r.get("issue") == "zero_records"]
    low = [r for r in results if r.get("issue") == "low_completeness"]
    print(f"\nDone: {len(results)} files, {len(issues)} issues")
    print(f"  zero_records: {len(zero)}")
    print(f"  low_completeness: {len(low)}")
    print(f"  errors: {len([r for r in results if r.get('error')])}")
    print(f"Report: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
