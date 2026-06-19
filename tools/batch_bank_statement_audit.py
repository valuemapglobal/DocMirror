#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Batch parse bank_statement fixtures and emit structured audit JSON."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sys
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests/fixtures/bank_statement"
REPORT_PATH = REPO / "artifacts/bank_statement_batch_audit.json"


def is_clean(p: Path) -> bool:
    n = p.stem.lower()
    return "cleaned" in n or n.endswith("_clean") or "_clean_" in n


def copy_base_stem(stem: str) -> str:
    while True:
        m = re.match(r"^(.*)_(\d+)$", stem)
        if not m:
            break
        stem = m.group(1)
    return stem


def select_fixtures(root: Path) -> list[Path]:
    pdfs = sorted(root.rglob("*.pdf"))
    pdfs = [p for p in pdfs if not is_clean(p)]

    stems = {p.stem for p in pdfs}
    filtered: list[Path] = []
    for p in pdfs:
        base = copy_base_stem(p.stem)
        if p.stem != base and base in stems:
            continue  # skip numeric copy when canonical exists
        filtered.append(p)

    by_hash: dict[str, Path] = {}
    for p in filtered:
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        if h not in by_hash:
            by_hash[h] = p
    return sorted(by_hash.values(), key=lambda x: x.name)


SEV_ORDER = {"OK": 0, "P2": 1, "P1": 2, "P0": 3}


def _bump_severity(current: str, new: str) -> str:
    return new if SEV_ORDER[new] > SEV_ORDER[current] else current


def analyze_case(name: str, mirror, community: dict | None, error: str | None) -> dict:
    if error:
        return {"file": name, "error": error, "severity": "P0", "issues": ["parse_error"]}

    meta = {}
    spe = {}
    if hasattr(mirror, "parser_info") and mirror.parser_info:
        spe = mirror.parser_info.structure or {}
    # API-style meta from to_api_dict if needed
    api = mirror.to_api_dict() if hasattr(mirror, "to_api_dict") else {}
    meta = api.get("meta") or {}

    pages = getattr(mirror, "pages", []) or []
    pt = sum(len(getattr(p, "tables", []) or []) for p in pages)
    mirror_rows = sum(
        len(getattr(t, "rows", []) or [])
        for p in pages
        for t in (getattr(p, "tables", []) or [])
    )
    logical = getattr(mirror, "logical_tables", []) or []
    lt_counts = [getattr(lt, "row_count", 0) or len(getattr(lt, "rows", []) or []) for lt in logical]

    props = (community or {}).get("document", {}).get("properties") or {}
    records = (community or {}).get("data", {}).get("records") or []
    warnings = (community or {}).get("status", {}).get("warnings") or []

    dirs = Counter(r.get("normalized", {}).get("direction") for r in records)
    dated = sum(1 for r in records if (r.get("normalized") or {}).get("date"))
    nonzero = sum(
        1
        for r in records
        if (r.get("normalized") or {}).get("amount") not in (None, 0, 0.0, "")
    )
    header_like = sum(
        1
        for r in records
        if str((r.get("raw") or {}).get("序号", "")).strip() in ("No.", "序号", "Bk.D.")
    )

    coverage = float(props.get("coverage_ratio") or 0)
    canonical_ratio = float(props.get("canonical_ratio") or coverage)
    extract_status = str(props.get("extract_status") or "")
    canonical_extracted = int(props.get("canonical_extracted") or 0)
    extracted = int(props.get("extracted_rows") or len(records))
    expected = int(props.get("expected_primary_rows") or 0)

    issues: list[str] = []
    severity = "OK"

    if community is None:
        issues.append("no_community_output")
        severity = "P0"
    mirror_type = getattr(mirror.entities, "document_type", "") or ""
    if (
        mirror_type not in ("bank_statement", "bank_reconciliation")
        and len(records) == 0
    ):
        issues.append(f"wrong_mirror_type:{mirror_type}")
        severity = _bump_severity(severity, "P1")
    if len(records) == 0:
        issues.append("zero_records")
        severity = _bump_severity(severity, "P0")
    if extract_status == "degraded":
        issues.append("cqf_degraded")
        severity = _bump_severity(severity, "P0")
    if "cqf_degraded:canonical_quality" in warnings or "error:cqf_degraded" in (
        (community or {}).get("status", {}).get("errors") or []
    ):
        issues.append("cqf_degraded_status")
        severity = _bump_severity(severity, "P0")
    if expected > 0 and canonical_ratio < 0.8:
        issues.append(f"low_canonical_ratio:{canonical_ratio:.2f}")
        severity = _bump_severity(severity, "P0")
    if "low_coverage:bank_ledger" in warnings or (expected > 0 and coverage < 0.8):
        issues.append(f"low_coverage:{coverage:.2f}")
        severity = _bump_severity(severity, "P0")
    if "missing_identity_field:account_holder" in warnings:
        issues.append("missing_account_holder")
        severity = _bump_severity(severity, "P2")
    if header_like > 0:
        issues.append(f"pipe_header_rows:{header_like}")
        severity = _bump_severity(severity, "P1")
    if extracted > 0 and nonzero == 0:
        issues.append("all_amounts_zero")
        severity = _bump_severity(severity, "P0")
    if extracted > 0 and canonical_extracted == 0:
        issues.append("no_canonical_rows")
        severity = _bump_severity(severity, "P0")
    elif extracted > 0 and dirs.get("other", 0) == extracted:
        issues.append("all_direction_other")
        severity = _bump_severity(severity, "P0")
    if extracted > 0 and dated < extracted * 0.5:
        issues.append(f"low_dated_ratio:{dated}/{extracted}")
        if dated < extracted * 0.3:
            severity = _bump_severity(severity, "P0")
        else:
            severity = _bump_severity(severity, "P1")
    if len(logical) > 1 and extracted < sum(lt_counts) * 0.5:
        issues.append(f"multi_lt_under_export:{extracted}/{sum(lt_counts)}")
        severity = _bump_severity(severity, "P0")
    if meta.get("physical_table_count") and int(meta.get("physical_table_count") or 0) > 0:
        if int(spe.get("physical_table_count") or 0) == 0:
            issues.append("spe_physical_count_mismatch")
            severity = _bump_severity(severity, "P2")

    ltqg = meta.get("ltqg") or {}
    mirror_expected = int(meta.get("mirror_expected_data_rows") or 0)
    if not mirror_expected and ltqg.get("enabled"):
        mirror_expected = int(ltqg.get("expected_data_rows") or 0)
    if ltqg.get("enabled") and int(ltqg.get("skipped_tables") or 0) > 0:
        issues.append(f"ltqg_skipped:{ltqg.get('skipped_tables')}")
        severity = _bump_severity(severity, "P2")
    if getattr(mirror.entities, "document_type", "") == "bank_reconciliation" and props.get("reconstruction_source"):
        issues.append("dti_plugin_type_split")

    spe_layer = spe.get("extraction_layer") or meta.get("extraction_method")
    if spe.get("competitors", {}).get("H_pipe_grid", 0) >= 0.85 and spe_layer != "pipe_delimited":
        issues.append("pipe_signal_not_pipe_layer")

    return {
        "file": name,
        "severity": severity,
        "issues": issues,
        "mirror_type": getattr(mirror.entities, "document_type", None),
        "pages": len(pages),
        "physical_tables": pt,
        "mirror_rows": mirror_rows,
        "logical_tables": len(logical),
        "logical_row_counts": lt_counts,
        "spe_primary": spe.get("primary"),
        "spe_layer": spe_layer,
        "H_pipe_grid": (spe.get("competitors") or {}).get("H_pipe_grid"),
        "style_id": props.get("style_id"),
        "reconstruction_source": props.get("reconstruction_source"),
        "expected_rows": expected,
        "extracted_rows": extracted,
        "coverage": round(coverage, 4),
        "canonical_ratio": round(canonical_ratio, 4),
        "canonical_extracted": canonical_extracted,
        "extract_status": extract_status,
        "records": len(records),
        "dated_rows": dated,
        "nonzero_amount": nonzero,
        "header_like_rows": header_like,
        "directions": dict(dirs),
        "warnings": warnings,
        "institution_hint": props.get("institution_hint"),
        "ltqg_enabled": bool(ltqg.get("enabled")),
        "mirror_expected_rows": mirror_expected,
    }


async def run_one(path: Path) -> dict:
    from docmirror.core.entry.factory import PerceiveOptions, perceive_document
    from docmirror.plugins.runner import (
        _plugin_document_type,
        _run_community_extract,
        run_plugin_extract_sync,
    )

    name = path.name
    try:
        result = await perceive_document(
            path,
            PerceiveOptions(enhance_mode="standard", editions=["community"]),
        )
        mirror = result.mirror
        community = (result.editions or {}).get("community")
        doc_type = getattr(mirror.entities, "document_type", "") or ""
        plugin_type = _plugin_document_type(mirror, doc_type)
        # Bank fixture audit SSOT: measure bank_statement plugin, not MEP routing alone.
        bank_community = _run_community_extract(
            mirror,
            "bank_statement",
            mirror.full_text or "",
        )
        if bank_community is not None:
            bank_records = ((bank_community.get("data") or {}).get("records") or [])
            existing_records = (
                ((community or {}).get("data") or {}).get("records") or []
                if community
                else []
            )
            if len(bank_records) >= len(existing_records):
                community = bank_community
        if community is None and plugin_type != "bank_statement":
            community = _run_community_extract(
                mirror,
                plugin_type,
                mirror.full_text or "",
            )
        if community is None:
            community = run_plugin_extract_sync(
                mirror,
                edition="community",
                full_text=mirror.full_text or "",
                file_path=str(path),
            )
        return analyze_case(name, mirror, community, None)
    except Exception as exc:
        return analyze_case(name, None, None, f"{type(exc).__name__}: {exc}")


async def main() -> int:
    fixtures = select_fixtures(FIXTURES)
    print(f"Selected {len(fixtures)} fixtures", flush=True)
    results: list[dict] = []
    for i, path in enumerate(fixtures, 1):
        print(f"[{i}/{len(fixtures)}] {path.name}", flush=True)
        row = await run_one(path)
        results.append(row)
        ok = sum(1 for r in results if r.get("severity") == "OK")
        print(
            f"  -> {row.get('severity')} records={row.get('records', 0)} "
            f"canonical={row.get('canonical_ratio', 0)} running_ok={ok}/{len(results)}",
            flush=True,
        )

    summary = Counter(r["severity"] for r in results)
    issue_counts = Counter()
    for r in results:
        for iss in r.get("issues") or []:
            issue_counts[iss.split(":")[0]] += 1

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fixture_count": len(fixtures),
        "summary": dict(summary),
        "issue_type_counts": dict(issue_counts.most_common()),
        "results": results,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {REPORT_PATH}", flush=True)
    print("Summary:", dict(summary), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
