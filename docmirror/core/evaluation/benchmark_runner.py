# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""Benchmark runner with regression delta reporting."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from docmirror.core.evaluation.golden_loader import GoldenCase, load_golden_matrix
from docmirror.core.evaluation.metrics import compute_metrics
from docmirror.models.entities.quality_report import ParseQualityReport


async def run_single_case(case: GoldenCase, parse_fn) -> ParseQualityReport:
    """Parse one golden case and compute metrics."""
    result = await parse_fn(case.file_path)
    expected = case.expected
    expected_domain = expected.get("domain_fields") or expected.get("derived_variables")
    if expected_domain is None:
        meta = expected.get("metadata") or {}
        if isinstance(meta, dict):
            expected_domain = meta.get("derived_variables")
    metrics = compute_metrics(
        result,
        original_text=expected.get("original_text") or result.full_text,
        expected_kv=expected.get("key_values"),
        expected_table_cols=expected.get("table_cols", 0),
        expected_domain_fields=expected_domain if isinstance(expected_domain, dict) else None,
    )
    failures = []
    for metric_name, threshold in expected.get("thresholds", {}).items():
        actual = metrics.get(metric_name)
        if actual is not None and actual < threshold:
            failures.append(
                {
                    "metric": metric_name,
                    "expected_min": threshold,
                    "actual": actual,
                }
            )
    min_txns = expected.get("min_transactions")
    if min_txns is not None:
        actual_txns = metrics.get("transaction_row_count", 0)
        if actual_txns < float(min_txns):
            failures.append(
                {
                    "metric": "transaction_row_count",
                    "expected_min": float(min_txns),
                    "actual": actual_txns,
                }
            )
    return ParseQualityReport(
        document_id=case.id,
        parser_version=getattr(result.parser_info, "parser_version", ""),
        metrics=metrics,
        failures=failures,
        warnings=[],
    )


async def run_benchmark_matrix(
    parse_fn,
    *,
    golden_root: Path | None = None,
    baseline_path: Path | None = None,
    include_tags: set[str] | None = None,
    exclude_tags: set[str] | None = None,
    case_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Run full golden matrix and optionally compute regression delta."""
    cases = load_golden_matrix(golden_root)
    reports: list[ParseQualityReport] = []
    for case in cases:
        if case_ids is not None and case.id not in case_ids:
            continue
        if include_tags is not None and not include_tags.intersection(set(case.tags)):
            continue
        if exclude_tags is not None and exclude_tags.intersection(set(case.tags)):
            continue
        if not case.file_path.exists():
            continue
        report = await run_single_case(case, parse_fn)
        reports.append(report)

    # Aggregate metrics
    aggregated: dict[str, list[float]] = {}
    for r in reports:
        for k, v in r.metrics.items():
            aggregated.setdefault(k, []).append(v)

    summary = {k: sum(v) / len(v) for k, v in aggregated.items() if v}

    regression_delta: dict[str, float] = {}
    if baseline_path and baseline_path.exists():
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        base_metrics = baseline.get("summary", {})
        for k, v in summary.items():
            if k in base_metrics:
                regression_delta[k] = v - base_metrics[k]

    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "case_count": len(reports),
        "summary": summary,
        "regression_delta": regression_delta,
        "reports": [r.model_dump() for r in reports],
        "failed_cases": [r.document_id for r in reports if r.failures],
    }
    return output


def save_benchmark_result(result: dict[str, Any], output_dir: Path) -> Path:
    """Persist benchmark run result."""
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = output_dir / f"benchmark_{ts}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
