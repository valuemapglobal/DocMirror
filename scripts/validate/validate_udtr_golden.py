#!/usr/bin/env python3
"""Validate metadata-only UDTR golden manifests against Mirror JSON outputs."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def validate_manifest_file(
    path: Path, *, base_dir: Path | None = None, allow_missing_private: bool = True
) -> list[str]:
    base_dir = base_dir or path.parent
    manifest = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if manifest.get("manifest_version") != "1.0":
        errors.append("manifest_version must be 1.0")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        errors.append("cases must be a non-empty list")
        return errors
    loaded_mirrors: dict[str, dict[str, Any]] = {}
    for index, case in enumerate(cases):
        errors.extend(_validate_case(case, index=index, base_dir=base_dir, allow_missing_private=allow_missing_private))
        case_id = str(case.get("case_id") or f"case:{index}")
        mirror = _load_case_mirror(case, base_dir=base_dir, allow_missing_private=allow_missing_private)
        if mirror is not None:
            loaded_mirrors[case_id] = mirror
    errors.extend(_validate_parity_groups(manifest.get("parity_groups") or [], loaded_mirrors))
    return errors


def summarize_manifest_file(
    path: Path,
    *,
    base_dir: Path | None = None,
    allow_missing_private: bool = True,
) -> dict[str, Any]:
    """Return an aggregate quality summary for a metadata-only golden manifest."""

    base_dir = base_dir or path.parent
    manifest = json.loads(path.read_text(encoding="utf-8"))
    cases = manifest.get("cases")
    case_list = cases if isinstance(cases, list) else []
    summary: dict[str, Any] = {
        "manifest_version": manifest.get("manifest_version"),
        "case_count": len(case_list),
        "loaded_case_count": 0,
        "skipped_case_count": 0,
        "failed_case_count": 0,
        "case_status_counts": {},
        "gate_status_counts": {},
        "quality_event_status_counts": {},
        "quality_event_severity_counts": {},
        "profile_totals": {
            "page_count": 0,
            "region_count": 0,
            "block_count": 0,
            "edge_count": 0,
            "quality_gate_count": 0,
            "quality_event_count": 0,
        },
        "parity_group_count": len(manifest.get("parity_groups") or []),
        "validation_error_count": 0,
        "cases": [],
    }
    case_status_counts: Counter[str] = Counter()
    gate_status_counts: Counter[str] = Counter()
    event_status_counts: Counter[str] = Counter()
    event_severity_counts: Counter[str] = Counter()
    validation_error_count = 0

    for index, case in enumerate(case_list):
        case_id = str(case.get("case_id") or f"case:{index}")
        mirror = _load_case_mirror(case, base_dir=base_dir, allow_missing_private=allow_missing_private)
        case_errors = _validate_case(case, index=index, base_dir=base_dir, allow_missing_private=allow_missing_private)
        validation_error_count += len(case_errors)
        if mirror is None:
            status = (
                "skipped"
                if _case_can_skip_missing(case, base_dir=base_dir, allow_missing_private=allow_missing_private)
                else "missing_or_invalid"
            )
            if status == "skipped":
                summary["skipped_case_count"] += 1
            else:
                summary["failed_case_count"] += 1
            case_status_counts[status] += 1
            summary["cases"].append({"case_id": case_id, "status": status, "error_count": len(case_errors)})
            continue

        status = "passed" if not case_errors else "failed"
        case_status_counts[status] += 1
        summary["loaded_case_count"] += 1
        if case_errors:
            summary["failed_case_count"] += 1
        quality = mirror.get("quality", {}) or {}
        gates = quality.get("gates") or []
        events = quality.get("events") or []
        profile = _udtr_profile_summary(mirror) or {}
        gate_status_counts.update(str(gate.get("status") or "unknown") for gate in gates if isinstance(gate, dict))
        event_status_counts.update(str(event.get("status") or "unknown") for event in events if isinstance(event, dict))
        event_severity_counts.update(
            str(event.get("severity") or "unknown") for event in events if isinstance(event, dict)
        )
        for key in summary["profile_totals"]:
            summary["profile_totals"][key] += _int_or_default(profile.get(key), 0)
        summary["cases"].append(
            {
                "case_id": case_id,
                "status": status,
                "error_count": len(case_errors),
                "page_count": len(mirror.get("pages", []) or []),
                "block_count": len(mirror.get("blocks", []) or []),
                "gate_count": len(gates),
                "quality_event_count": len(events),
            }
        )

    parity_errors = _validate_parity_groups(
        manifest.get("parity_groups") or [], _loaded_case_mirrors(case_list, base_dir, allow_missing_private)
    )
    validation_error_count += len(parity_errors)
    if parity_errors:
        summary["failed_case_count"] += 1
    summary["case_status_counts"] = dict(sorted(case_status_counts.items()))
    summary["gate_status_counts"] = dict(sorted(gate_status_counts.items()))
    summary["quality_event_status_counts"] = dict(sorted(event_status_counts.items()))
    summary["quality_event_severity_counts"] = dict(sorted(event_severity_counts.items()))
    summary["validation_error_count"] = validation_error_count
    summary["parity_error_count"] = len(parity_errors)
    return summary


def validate_mirror_against_expectations(mirror: dict[str, Any], expectations: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if expectations.get("canonical_shape"):
        errors.extend(_validate_canonical_shape(mirror))
    if "page_count" in expectations and len(mirror.get("pages", []) or []) != int(expectations["page_count"]):
        errors.append(f"page_count expected {expectations['page_count']} got {len(mirror.get('pages', []) or [])}")
    if "min_table_count" in expectations:
        count = sum(1 for block in mirror.get("blocks", []) or [] if block.get("type") == "table")
        if count < int(expectations["min_table_count"]):
            errors.append(f"table_count expected >= {expectations['min_table_count']} got {count}")
    if "max_residual_ratio" in expectations:
        ratio = float((mirror.get("quality", {}) or {}).get("coverage", {}).get("residual_ratio", 0.0) or 0.0)
        if ratio > float(expectations["max_residual_ratio"]):
            errors.append(f"residual_ratio expected <= {expectations['max_residual_ratio']} got {ratio}")
    errors.extend(_validate_required_gates(mirror, expectations.get("required_gates") or {}))
    errors.extend(_validate_required_rotations(mirror, expectations.get("required_page_rotations") or {}))
    errors.extend(_validate_required_relation_kinds(mirror, expectations.get("required_relation_kinds") or {}))
    errors.extend(
        _validate_required_statement_structures(mirror, expectations.get("required_statement_structures") or [])
    )
    errors.extend(_validate_verification_expectations(mirror, expectations.get("verification") or {}))
    errors.extend(_validate_quality_event_expectations(mirror, expectations.get("quality_events") or {}))
    errors.extend(_validate_profile_summary_expectations(mirror, expectations.get("profile_summary") or {}))
    errors.extend(_validate_text_probes(mirror, expectations.get("required_text_probes") or []))
    return errors


def _validate_canonical_shape(mirror: dict[str, Any]) -> list[str]:
    required_keys = {
        "mirror",
        "source",
        "document",
        "pages",
        "evidence",
        "regions",
        "blocks",
        "graph",
        "semantics",
        "quality",
        "diagnostics",
        "assets",
    }
    missing = sorted(required_keys - set(mirror))
    errors = [f"canonical_shape missing top-level keys: {missing}"] if missing else []
    if (mirror.get("mirror") or {}).get("schema") != "docmirror.mirror_json":
        errors.append(
            f"canonical_shape mirror.schema expected docmirror.mirror_json got {(mirror.get('mirror') or {}).get('schema')}"
        )
    if not isinstance(mirror.get("pages"), list):
        errors.append("canonical_shape pages must be a list")
    if not isinstance(mirror.get("blocks"), list):
        errors.append("canonical_shape blocks must be a list")
    if not isinstance((mirror.get("graph") or {}).get("edges"), list):
        errors.append("canonical_shape graph.edges must be a list")
    if not isinstance((mirror.get("quality") or {}).get("gates"), list):
        errors.append("canonical_shape quality.gates must be a list")
    return errors


def _validate_case(
    case: dict[str, Any],
    *,
    index: int,
    base_dir: Path,
    allow_missing_private: bool,
) -> list[str]:
    errors: list[str] = []
    case_id = str(case.get("case_id") or f"case:{index}")
    output_path = case.get("mirror_output")
    if not output_path:
        return [f"{case_id}: mirror_output is required"]
    path = Path(output_path)
    if not path.is_absolute():
        path = base_dir / path
    if not path.exists():
        if allow_missing_private and (case.get("private_source") is True or case.get("skip_if_missing") is True):
            return []
        return [f"{case_id}: mirror_output not found: {path}"]
    try:
        mirror = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"{case_id}: failed to read mirror_output: {exc}"]
    for message in validate_mirror_against_expectations(mirror, case.get("expectations") or {}):
        errors.append(f"{case_id}: {message}")
    return errors


def _load_case_mirror(
    case: dict[str, Any],
    *,
    base_dir: Path,
    allow_missing_private: bool,
) -> dict[str, Any] | None:
    output_path = case.get("mirror_output")
    if not output_path:
        return None
    path = Path(output_path)
    if not path.is_absolute():
        path = base_dir / path
    if not path.exists():
        if allow_missing_private and (case.get("private_source") is True or case.get("skip_if_missing") is True):
            return None
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return loaded if isinstance(loaded, dict) else None


def _loaded_case_mirrors(
    cases: list[dict[str, Any]],
    base_dir: Path,
    allow_missing_private: bool,
) -> dict[str, dict[str, Any]]:
    loaded: dict[str, dict[str, Any]] = {}
    for index, case in enumerate(cases):
        case_id = str(case.get("case_id") or f"case:{index}")
        mirror = _load_case_mirror(case, base_dir=base_dir, allow_missing_private=allow_missing_private)
        if mirror is not None:
            loaded[case_id] = mirror
    return loaded


def _case_can_skip_missing(case: dict[str, Any], *, base_dir: Path, allow_missing_private: bool) -> bool:
    output_path = case.get("mirror_output")
    if not output_path:
        return False
    path = Path(output_path)
    if not path.is_absolute():
        path = base_dir / path
    return bool(
        allow_missing_private
        and not path.exists()
        and (case.get("private_source") is True or case.get("skip_if_missing") is True)
    )


def _validate_parity_groups(groups: list[dict[str, Any]], mirrors: dict[str, dict[str, Any]]) -> list[str]:
    if not groups:
        return []
    if not isinstance(groups, list):
        return ["parity_groups must be a list"]
    errors: list[str] = []
    for index, group in enumerate(groups):
        if not isinstance(group, dict):
            errors.append(f"parity_group:{index}: group must be an object")
            continue
        group_id = str(group.get("group_id") or f"parity_group:{index}")
        case_ids = [str(case_id) for case_id in group.get("case_ids") or [] if str(case_id)]
        if not case_ids:
            errors.append(f"{group_id}: case_ids must be a non-empty list")
            continue
        present = [(case_id, mirrors[case_id]) for case_id in case_ids if case_id in mirrors]
        required_present = int(group.get("required_present_count", len(case_ids)) or 0)
        if len(present) < required_present:
            errors.append(f"{group_id}: required_present_count expected >= {required_present} got {len(present)}")
            continue
        if len(present) < 2:
            continue
        checks = _parity_checks(group.get("compare"))
        base_case_id, base_mirror = present[0]
        base_signatures = {check: _parity_signature(base_mirror, check) for check in checks}
        for case_id, mirror in present[1:]:
            for check in checks:
                actual = _parity_signature(mirror, check)
                expected = base_signatures[check]
                if actual != expected:
                    errors.append(
                        f"{group_id}: {check} mismatch for {case_id}; "
                        f"expected {expected} from {base_case_id} got {actual}"
                    )
    return errors


def _parity_checks(compare: Any) -> list[str]:
    if compare is None:
        return ["canonical_shape", "page_count", "block_type_counts", "region_kind_counts", "quality_gate_statuses"]
    if isinstance(compare, list):
        return [str(item) for item in compare if str(item)]
    if isinstance(compare, dict):
        return [str(key) for key, enabled in compare.items() if enabled]
    return [str(compare)]


def _parity_signature(mirror: dict[str, Any], check: str) -> Any:
    if check == "canonical_shape":
        required = {
            "mirror",
            "source",
            "document",
            "pages",
            "evidence",
            "regions",
            "blocks",
            "graph",
            "semantics",
            "quality",
            "diagnostics",
            "assets",
        }
        return {
            "keys": sorted(required & set(mirror)),
            "schema": (mirror.get("mirror") or {}).get("schema"),
        }
    if check == "page_count":
        return len(mirror.get("pages", []) or [])
    if check == "block_type_counts":
        return dict(
            sorted(Counter(str(block.get("type") or "unknown") for block in mirror.get("blocks", []) or []).items())
        )
    if check == "region_kind_counts":
        return dict(
            sorted(Counter(str(region.get("kind") or "unknown") for region in mirror.get("regions", []) or []).items())
        )
    if check == "quality_gate_statuses":
        return {
            str(gate.get("id")): str(gate.get("status") or "")
            for gate in (mirror.get("quality", {}) or {}).get("gates", []) or []
            if gate.get("id")
        }
    if check == "event_summary":
        summary = (mirror.get("quality", {}) or {}).get("event_summary") or {}
        return {
            "event_count": summary.get("event_count"),
            "actionable_count": summary.get("actionable_count"),
            "by_status": summary.get("by_status") or {},
            "by_severity": summary.get("by_severity") or {},
        }
    if check == "profile_counts":
        profile = _udtr_profile_summary(mirror) or {}
        return {
            "page_count": profile.get("page_count"),
            "region_count": profile.get("region_count"),
            "block_count": profile.get("block_count"),
            "quality_gate_count": profile.get("quality_gate_count"),
            "quality_event_count": profile.get("quality_event_count"),
        }
    return None


def _validate_required_gates(mirror: dict[str, Any], required: dict[str, str | list[str]]) -> list[str]:
    gates = {gate.get("id"): gate.get("status") for gate in (mirror.get("quality", {}) or {}).get("gates", []) or []}
    errors: list[str] = []
    for gate_id, expected in required.items():
        actual = gates.get(gate_id)
        allowed = [expected] if isinstance(expected, str) else list(expected)
        if actual not in allowed:
            errors.append(f"{gate_id} expected status in {allowed} got {actual}")
    return errors


def _validate_required_rotations(mirror: dict[str, Any], required: dict[str, int]) -> list[str]:
    by_number = {str(page.get("page_number")): page for page in mirror.get("pages", []) or []}
    errors: list[str] = []
    for page_number, expected in required.items():
        page = by_number.get(str(page_number))
        if not page:
            errors.append(f"page {page_number} missing for rotation check")
            continue
        normalization = (page.get("coordinate_transform") or {}).get("page_normalization") or {}
        actual = int(normalization.get("selected_rotation", page.get("normalized_rotation", 0)) or 0)
        if actual != int(expected):
            errors.append(f"page {page_number} rotation expected {expected} got {actual}")
    return errors


def _validate_required_relation_kinds(mirror: dict[str, Any], required: dict[str, int]) -> list[str]:
    counts: dict[str, int] = {}
    for edge in (mirror.get("graph", {}) or {}).get("edges", []) or []:
        relation_kind = (edge.get("metadata") or {}).get("relation_kind")
        if relation_kind:
            counts[str(relation_kind)] = counts.get(str(relation_kind), 0) + 1
    errors: list[str] = []
    for relation_kind, minimum in required.items():
        actual = counts.get(str(relation_kind), 0)
        if actual < int(minimum):
            errors.append(f"relation_kind {relation_kind} expected >= {minimum} got {actual}")
    return errors


def _validate_required_statement_structures(mirror: dict[str, Any], required: list[dict[str, Any]]) -> list[str]:
    if not required:
        return []
    page_id_by_number = {
        str(page.get("page_number")): str(page.get("page_id") or "") for page in mirror.get("pages", []) or []
    }
    table_blocks = [block for block in mirror.get("blocks", []) or [] if block.get("type") == "table"]
    errors: list[str] = []
    for spec in required:
        page_number = str(spec.get("page_number") or spec.get("page") or "")
        page_id = page_id_by_number.get(page_number)
        if page_number and not page_id:
            errors.append(f"statement_structure page {page_number} missing")
            continue
        candidates = [
            block
            for block in table_blocks
            if (not page_id or page_id in (block.get("page_ids") or []))
            and isinstance((block.get("content") or {}).get("statement_structure"), dict)
        ]
        expected_type = spec.get("statement_type")
        if expected_type:
            candidates = [
                block
                for block in candidates
                if ((block.get("content") or {}).get("statement_structure") or {}).get("statement_type")
                == expected_type
            ]
        if not candidates:
            errors.append(f"statement_structure not found for page {page_number or '*'} type {expected_type or '*'}")
            continue
        if "min_rule_count" in spec:
            minimum = int(spec["min_rule_count"])
            actual = max(
                len(((block.get("content") or {}).get("statement_structure") or {}).get("rules") or [])
                for block in candidates
            )
            if actual < minimum:
                errors.append(
                    f"statement_structure page {page_number or '*'} rule_count expected >= {minimum} got {actual}"
                )
        if "rule_validation_status" in spec:
            allowed = spec["rule_validation_status"]
            allowed_statuses = [str(allowed)] if isinstance(allowed, str) else [str(item) for item in allowed]
            actual_statuses = _statement_rule_validation_statuses(candidates)
            if not any(status in allowed_statuses for status in actual_statuses):
                errors.append(
                    f"statement_structure page {page_number or '*'} rule_validation_status expected "
                    f"in {allowed_statuses} got {actual_statuses}"
                )
        if "min_account_rows" in spec:
            minimum = int(spec["min_account_rows"])
            actual = max(
                len(((block.get("content") or {}).get("statement_structure") or {}).get("account_rows") or [])
                for block in candidates
            )
            if actual < minimum:
                errors.append(
                    f"statement_structure page {page_number or '*'} account_rows expected >= {minimum} got {actual}"
                )
        if "requires_review" in spec:
            expected = bool(spec["requires_review"])
            actual_values = [
                bool(
                    (((block.get("content") or {}).get("statement_structure") or {}).get("quality") or {}).get(
                        "requires_review"
                    )
                )
                for block in candidates
            ]
            if expected not in actual_values:
                errors.append(
                    f"statement_structure page {page_number or '*'} requires_review expected {expected} got {actual_values}"
                )
    return errors


def _validate_verification_expectations(mirror: dict[str, Any], required: dict[str, Any]) -> list[str]:
    if not required:
        return []
    verification = (mirror.get("quality") or {}).get("verification") or {}
    errors: list[str] = []
    _validate_minimum(errors, "verification.unit_count", verification.get("unit_count"), required.get("min_unit_count"))
    _validate_minimum(
        errors,
        "verification.applicable_unit_count",
        verification.get("applicable_unit_count"),
        required.get("min_applicable_unit_count"),
    )
    _validate_minimum(
        errors,
        "verification.verified_unit_ratio",
        verification.get("verified_unit_ratio"),
        required.get("min_verified_unit_ratio"),
    )
    _validate_maximum(
        errors,
        "verification.conflict_ratio",
        verification.get("conflict_ratio"),
        required.get("max_conflict_ratio"),
    )
    _validate_required_count_map(
        errors,
        "verification.unit_type_counts",
        verification.get("unit_type_counts") or {},
        required.get("required_unit_type_counts") or {},
    )
    _validate_required_count_map(
        errors,
        "verification.candidate_source_counts",
        verification.get("candidate_source_counts") or {},
        required.get("required_candidate_source_counts") or {},
    )
    _validate_required_count_map(
        errors,
        "verification.claim_type_counts",
        verification.get("claim_type_counts") or {},
        required.get("required_claim_type_counts") or {},
    )
    crop_ocr_required = required.get("crop_ocr")
    if isinstance(crop_ocr_required, dict):
        crop_ocr = verification.get("crop_ocr") if isinstance(verification.get("crop_ocr"), dict) else {}
        if crop_ocr_required.get("status") and crop_ocr.get("status") != crop_ocr_required.get("status"):
            errors.append(
                f"verification.crop_ocr.status expected {crop_ocr_required.get('status')} got {crop_ocr.get('status')}"
            )
        _validate_minimum(
            errors,
            "verification.crop_ocr.processed_count",
            crop_ocr.get("processed_count"),
            crop_ocr_required.get("min_processed_count"),
        )
        _validate_minimum(
            errors,
            "verification.crop_ocr.agreement_count",
            crop_ocr.get("agreement_count"),
            crop_ocr_required.get("min_agreement_count"),
        )
        _validate_maximum(
            errors,
            "verification.crop_ocr.conflict_count",
            crop_ocr.get("conflict_count"),
            crop_ocr_required.get("max_conflict_count"),
        )
    return errors


def _validate_quality_event_expectations(mirror: dict[str, Any], required: dict[str, Any]) -> list[str]:
    if not required:
        return []
    quality = mirror.get("quality", {}) or {}
    events = quality.get("events") or []
    events = events if isinstance(events, list) else []
    summary = quality.get("event_summary") if isinstance(quality.get("event_summary"), dict) else {}
    errors: list[str] = []
    _validate_minimum(errors, "quality.events.event_count", len(events), required.get("min_event_count"))
    _validate_maximum(errors, "quality.events.event_count", len(events), required.get("max_event_count"))
    actionable_count = sum(1 for event in events if isinstance(event, dict) and event.get("actionable") is True)
    _validate_minimum(errors, "quality.events.actionable_count", actionable_count, required.get("min_actionable_count"))
    _validate_maximum(errors, "quality.events.actionable_count", actionable_count, required.get("max_actionable_count"))
    _validate_required_count_map(
        errors,
        "quality.events.status_counts",
        dict(Counter(str(event.get("status") or "unknown") for event in events if isinstance(event, dict))),
        required.get("required_status_counts") or {},
    )
    _validate_required_count_map(
        errors,
        "quality.events.severity_counts",
        dict(Counter(str(event.get("severity") or "unknown") for event in events if isinstance(event, dict))),
        required.get("required_severity_counts") or {},
    )
    if required.get("summary_matches_events"):
        _validate_event_summary_matches_events(errors, events, summary)
    return errors


def _validate_event_summary_matches_events(
    errors: list[str],
    events: list[Any],
    summary: dict[str, Any],
) -> None:
    event_dicts = [event for event in events if isinstance(event, dict)]
    actionable_count = sum(1 for event in event_dicts if event.get("actionable") is True)
    status_counts = dict(Counter(str(event.get("status") or "unknown") for event in event_dicts))
    severity_counts = dict(Counter(str(event.get("severity") or "unknown") for event in event_dicts))
    if _int_or_default(summary.get("event_count"), -1) != len(event_dicts):
        errors.append(f"quality.event_summary.event_count expected {len(event_dicts)} got {summary.get('event_count')}")
    if _int_or_default(summary.get("actionable_count"), -1) != actionable_count:
        errors.append(
            f"quality.event_summary.actionable_count expected {actionable_count} got {summary.get('actionable_count')}"
        )
    if dict(summary.get("by_status") or {}) != status_counts:
        errors.append(f"quality.event_summary.by_status expected {status_counts} got {summary.get('by_status')}")
    if dict(summary.get("by_severity") or {}) != severity_counts:
        errors.append(f"quality.event_summary.by_severity expected {severity_counts} got {summary.get('by_severity')}")


def _validate_profile_summary_expectations(mirror: dict[str, Any], required: dict[str, Any]) -> list[str]:
    if not required:
        return []
    profile = _udtr_profile_summary(mirror)
    if profile is None:
        return ["profile_summary expected udtr_profile_summary diagnostics stage"]
    errors: list[str] = []
    _validate_minimum(errors, "profile_summary.page_count", profile.get("page_count"), required.get("min_page_count"))
    _validate_minimum(
        errors, "profile_summary.region_count", profile.get("region_count"), required.get("min_region_count")
    )
    _validate_minimum(
        errors, "profile_summary.block_count", profile.get("block_count"), required.get("min_block_count")
    )
    _validate_minimum(errors, "profile_summary.edge_count", profile.get("edge_count"), required.get("min_edge_count"))
    _validate_minimum(
        errors,
        "profile_summary.quality_gate_count",
        profile.get("quality_gate_count"),
        required.get("min_quality_gate_count"),
    )
    _validate_minimum(
        errors,
        "profile_summary.quality_event_count",
        profile.get("quality_event_count"),
        required.get("min_quality_event_count"),
    )
    _validate_required_count_map(
        errors,
        "profile_summary.evidence_atom_counts",
        profile.get("evidence_atom_counts") or {},
        required.get("required_evidence_atom_counts") or {},
    )
    return errors


def _udtr_profile_summary(mirror: dict[str, Any]) -> dict[str, Any] | None:
    pipeline = (mirror.get("diagnostics", {}) or {}).get("pipeline") or []
    for entry in pipeline:
        if isinstance(entry, dict) and entry.get("stage") == "udtr_profile_summary":
            return entry
    return None


def _int_or_default(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _validate_minimum(errors: list[str], label: str, actual: Any, expected: Any) -> None:
    if expected is None:
        return
    try:
        actual_value = float(actual)
        expected_value = float(expected)
    except (TypeError, ValueError):
        errors.append(f"{label} expected >= {expected} got {actual}")
        return
    if actual_value < expected_value:
        errors.append(f"{label} expected >= {expected} got {actual}")


def _validate_maximum(errors: list[str], label: str, actual: Any, expected: Any) -> None:
    if expected is None:
        return
    try:
        actual_value = float(actual)
        expected_value = float(expected)
    except (TypeError, ValueError):
        errors.append(f"{label} expected <= {expected} got {actual}")
        return
    if actual_value > expected_value:
        errors.append(f"{label} expected <= {expected} got {actual}")


def _validate_required_count_map(
    errors: list[str],
    label: str,
    actual: dict[str, Any],
    required: dict[str, Any],
) -> None:
    for key, minimum in required.items():
        actual_count = actual.get(str(key), 0)
        try:
            actual_value = int(actual_count)
            minimum_value = int(minimum)
        except (TypeError, ValueError):
            errors.append(f"{label}.{key} expected >= {minimum} got {actual_count}")
            continue
        if actual_value < minimum_value:
            errors.append(f"{label}.{key} expected >= {minimum} got {actual_count}")


def _statement_rule_validation_statuses(blocks: list[dict[str, Any]]) -> list[str]:
    statuses: list[str] = []
    for block in blocks:
        structure = (block.get("content") or {}).get("statement_structure") or {}
        for rule in structure.get("rules") or []:
            if not isinstance(rule, dict):
                continue
            validation = rule.get("validation") if isinstance(rule.get("validation"), dict) else {}
            status = str(validation.get("status") or "not_evaluated")
            statuses.append(status)
    return sorted(set(statuses))


def _validate_text_probes(mirror: dict[str, Any], probes: list[str]) -> list[str]:
    haystack = "\n".join(str(block.get("text") or "") for block in mirror.get("blocks", []) or [])
    return [f"text probe missing: {probe}" for probe in probes if str(probe) not in haystack]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate metadata-only UDTR golden manifests")
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--strict-private",
        action="store_true",
        help="Fail when a private/skip-if-missing case output is absent.",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        help="Write an aggregate quality summary JSON for loaded manifest cases.",
    )
    args = parser.parse_args()
    if args.summary_json:
        summary = summarize_manifest_file(args.manifest, allow_missing_private=not args.strict_private)
        args.summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    errors = validate_manifest_file(args.manifest, allow_missing_private=not args.strict_private)
    if errors:
        print("UDTR golden validation FAILED")
        for error in errors:
            print(f"- {error}")
        return 1
    print("UDTR golden validation OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
