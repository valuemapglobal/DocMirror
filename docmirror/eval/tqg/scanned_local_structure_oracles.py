# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""TQG oracle for scanned local structure restoration."""

from __future__ import annotations

from typing import Any

from docmirror.eval.tqg.report import GateReport
from docmirror.models.mirror.vnext_access import iter_regions, iter_structures


def _doc_and_domain(mirror_or_api: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    if hasattr(mirror_or_api, "to_mirror_json_vnext"):
        api = mirror_or_api.to_mirror_json_vnext()
        doc = api if isinstance(api, dict) else {}
        entities = getattr(mirror_or_api, "entities", None)
        domain_specific = getattr(entities, "domain_specific", None) if entities is not None else None
        return doc, domain_specific if isinstance(domain_specific, dict) else {}
    if isinstance(mirror_or_api, dict):
        if mirror_or_api.get("pages"):
            return mirror_or_api, {}
        if isinstance(mirror_or_api.get("document"), dict) and mirror_or_api["document"].get("pages"):
            return mirror_or_api["document"], {}
        doc = ((mirror_or_api.get("data") or {}).get("document") or {}) if isinstance(mirror_or_api, dict) else {}
        domain = ((mirror_or_api.get("data") or {}).get("properties") or {}) if isinstance(mirror_or_api, dict) else {}
        return doc, domain if isinstance(domain, dict) else {}
    return {}, {}


def _field_grid_structures(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        *iter_structures(doc, kind="field_grid"),
        *iter_structures(doc, kind="label_value_graph"),
    ]


def run_scanned_local_structure_oracle(
    mirror_or_api: Any,
    spec: dict[str, Any],
    *,
    case_id: str = "",
    track: str = "",
    tier: str = "regression",
) -> GateReport:
    report = GateReport(case_id=case_id, track=track, tier=tier)
    doc, domain = _doc_and_domain(mirror_or_api)
    accounts = domain.get("credit_accounts") or []

    min_structures = int(spec.get("min_local_structures", 0) or 0)
    if min_structures:
        count = len(_field_grid_structures(doc))
        ok = count >= min_structures
        report.checks["scanned_local_structure_min_structures"] = ok
        report.metrics["local_structure_count"] = count
        if not ok:
            report.passed = False
            report.failures.append(f"local_structure_count expected >= {min_structures}, got {count}")

    min_accounts = int(spec.get("min_credit_accounts", 0) or 0)
    if min_accounts:
        ok = len(accounts) >= min_accounts
        report.checks["scanned_local_structure_min_credit_accounts"] = ok
        report.metrics["credit_account_count"] = len(accounts)
        if not ok:
            report.passed = False
            report.failures.append(f"credit_account_count expected >= {min_accounts}, got {len(accounts)}")

    required_fields = list(spec.get("required_account_fields") or [])
    if required_fields:
        ok = all(all(field in account for field in required_fields) for account in accounts)
        report.checks["scanned_local_structure_required_fields"] = ok
        if not ok:
            report.passed = False
            report.failures.append(f"expected every account to contain fields {required_fields}")

    if spec.get("require_field_bbox_refs"):
        ok = True
        for account in accounts:
            for key, value in account.items():
                if key in {"source", "page", "anchor", "bbox", "source_structure_id", "confidence", "audit"}:
                    continue
                if not isinstance(value, dict):
                    continue
                refs = value.get("source_refs") or {}
                has_refs = bool(value.get("bbox")) and bool(
                    refs.get("line_ids") or refs.get("token_ids") or refs.get("cell_id")
                )
                if not has_refs:
                    ok = False
                    break
        report.checks["scanned_local_structure_field_bbox_refs"] = ok
        if not ok:
            report.passed = False
            report.failures.append("expected mapped account fields to carry bbox and source_refs")

    prefer_kind = spec.get("prefer_structure_kind")
    if prefer_kind:
        kinds: set[str] = set()
        for structure in _field_grid_structures(doc):
            if isinstance(structure, dict) and structure.get("structure_kind"):
                kinds.add(str(structure.get("structure_kind")))
        for region in iter_regions(doc):
            structure = region.get("structure") or {}
            if isinstance(structure, dict) and structure.get("structure_kind"):
                kinds.add(str(structure.get("structure_kind")))
            elif region.get("kind") == "field_grid":
                kinds.add("field_grid")
        ok = prefer_kind in kinds
        report.checks["scanned_local_structure_prefer_kind"] = ok
        report.metrics["structure_kinds"] = sorted(k for k in kinds if k)
        if not ok:
            report.passed = False
            report.failures.append(f"expected structure_kind {prefer_kind}, got {sorted(kinds)}")

    expected = spec.get("expected_first_account") or {}
    if expected:
        first = accounts[0] if accounts else {}
        projected = {
            key: (first.get(key) or {}).get("value") if isinstance(first.get(key), dict) else first.get(key)
            for key in expected
        }
        ok = projected == expected
        report.checks["scanned_local_structure_expected_first_account"] = ok
        if not ok:
            report.passed = False
            report.failures.append(f"first account mismatch: expected {expected}, got {projected}")

    if spec.get("forbid_credit_accounts"):
        ok = not accounts
        report.checks["scanned_local_structure_forbid_credit_accounts"] = ok
        if not ok:
            report.passed = False
            report.failures.append(f"expected no credit_accounts, got {len(accounts)}")

    return report
