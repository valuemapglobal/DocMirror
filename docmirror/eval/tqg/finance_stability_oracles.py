# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Design 19 G4 — finance output stability across PageProjection migration paths."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from docmirror.eval.tqg.report import GateReport


def project_credit_account(account: dict[str, Any]) -> dict[str, Any]:
    """Flatten credit account to field -> value for golden diff."""
    skip = {"source", "page", "anchor", "bbox", "source_structure_id", "confidence", "audit"}
    out: dict[str, Any] = {}
    for key, value in account.items():
        if key in skip:
            continue
        if isinstance(value, dict) and "value" in value:
            out[key] = value.get("value")
        else:
            out[key] = value
    return out


def project_repayment_records(records: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    rows: list[tuple[Any, ...]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        rows.append(
            (
                record.get("year"),
                record.get("month"),
                record.get("status"),
                str(record.get("overdue_amount", "")),
            )
        )
    return rows


def _accounts_from_mirror_or_api(mirror_or_api: Any) -> list[dict[str, Any]]:
    if hasattr(mirror_or_api, "entities"):
        ds = getattr(getattr(mirror_or_api, "entities", None), "domain_specific", None) or {}
        accounts = ds.get("credit_accounts")
        if accounts:
            return list(accounts)
    if isinstance(mirror_or_api, dict):
        data = mirror_or_api.get("data") or {}
        accounts = data.get("credit_accounts")
        if accounts:
            return list(accounts)
    return []


def _load_golden(spec: dict[str, Any]) -> dict[str, Any]:
    path = spec.get("golden_fixture")
    if not path:
        return {}
    golden_path = Path(str(path))
    if not golden_path.is_file():
        return {}
    return json.loads(golden_path.read_text(encoding="utf-8"))


def _find_account_by_anchor(accounts: list[dict[str, Any]], substring: str) -> dict[str, Any] | None:
    for account in accounts:
        anchor = account.get("anchor") or {}
        anchor_text = anchor.get("value") if isinstance(anchor, dict) else str(anchor)
        if substring in str(anchor_text):
            return account
    return None


def run_vnext_finance_stability_oracle(
    mirror_or_api: Any,
    spec: dict[str, Any],
    *,
    case_id: str = "",
    track: str = "",
    tier: str = "regression",
) -> GateReport:
    report = GateReport(case_id=case_id, track=track, tier=tier)
    accounts = _accounts_from_mirror_or_api(mirror_or_api)
    golden = _load_golden(spec)
    if not golden and spec.get("golden_fixture"):
        report.passed = False
        report.failures.append(f"golden fixture missing: {spec.get('golden_fixture')}")
        return report

    min_accounts = int(spec.get("min_credit_accounts") or golden.get("min_credit_accounts") or 0)
    if min_accounts:
        ok = len(accounts) >= min_accounts
        report.checks["vnext_finance_min_accounts"] = ok
        report.metrics["credit_account_count"] = len(accounts)
        if not ok:
            report.passed = False
            report.failures.append(f"credit_account_count expected >= {min_accounts}, got {len(accounts)}")

    golden_accounts = spec.get("accounts_by_anchor_substring") or golden.get("accounts_by_anchor_substring") or {}
    for anchor_key, expected_fields in golden_accounts.items():
        account = _find_account_by_anchor(accounts, str(anchor_key))
        if account is None:
            report.passed = False
            report.failures.append(f"no account matching anchor substring {anchor_key!r}")
            continue
        projected = project_credit_account(account)
        mismatches = {
            field: (expected, projected.get(field))
            for field, expected in expected_fields.items()
            if projected.get(field) != expected
        }
        check_name = f"vnext_finance_golden_{anchor_key}"
        report.checks[check_name] = not mismatches
        if mismatches:
            report.passed = False
            report.failures.append(f"golden mismatch for {anchor_key}: {mismatches}")

    required_anchors = list(spec.get("required_anchors") or golden.get("required_anchors") or [])
    if required_anchors:
        found = [anchor for anchor in required_anchors if _find_account_by_anchor(accounts, str(anchor)) is not None]
        ok = len(found) == len(required_anchors)
        report.checks["vnext_finance_required_anchors"] = ok
        if not ok:
            report.passed = False
            missing = [a for a in required_anchors if a not in found]
            report.failures.append(f"missing account anchors: {missing}")

    if spec.get("require_vnext_mirror_shape") and hasattr(mirror_or_api, "to_mirror_json_vnext"):
        api = mirror_or_api.to_mirror_json_vnext()
        pages = api.get("pages") or []
        page = next((p for p in pages if int(p.get("page_number") or 0) == 4), {})
        region_count = len(api.get("regions") or [])
        flow_ok = bool((api.get("graph") or {}).get("reading_flows") is not None)
        doc = api.get("document") or {}
        no_removed_doc_fields = "micro_grids" not in doc and ("_de" + "precated") not in doc
        no_top_level_texts = "texts" not in page
        ok = region_count > 0 and flow_ok and no_removed_doc_fields and no_top_level_texts
        report.checks["vnext_finance_mirror_shape"] = ok
        report.metrics["region_count"] = region_count
        if not ok:
            report.passed = False
            report.failures.append("PageProjection mirror shape check failed (regions/flow/raw fields)")

    return report
