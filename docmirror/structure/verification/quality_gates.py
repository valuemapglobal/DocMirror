"""Quality gates for the universal evidence verification layer."""

from __future__ import annotations

from typing import Any

from docmirror.structure.verification.models import VerificationReport


def build_verification_quality_gates(report: VerificationReport) -> list[dict[str, Any]]:
    summary = report.summary()
    unit_count = int(summary.get("unit_count", 0) or 0)
    if unit_count == 0:
        return [
            _gate("gate:verification_unit_coverage", "not_applicable", 1.0, 0.9),
            _gate("gate:verification_value_confidence", "not_applicable", 1.0, 0.8),
            _gate("gate:verification_conflict_ratio", "not_applicable", 1.0, 1.0),
            _gate("gate:verification_rule_evaluability", "not_applicable", 1.0, 0.8),
            _gate("gate:verification_rule_validation", "not_applicable", 1.0, 0.8),
        ]

    verified_ratio = float(summary.get("verified_unit_ratio", 0.0) or 0.0)
    conflict_ratio = float(summary.get("conflict_ratio", 0.0) or 0.0)
    rule_counts = summary.get("rule_status_counts") if isinstance(summary.get("rule_status_counts"), dict) else {}
    rule_count = int(summary.get("rule_count", 0) or 0)
    pass_rules = int(rule_counts.get("pass", 0) or 0)
    warn_rules = int(rule_counts.get("warn", 0) or 0)
    not_evaluated_rules = int(rule_counts.get("not_evaluated", 0) or 0)
    rule_evaluable = (rule_count - not_evaluated_rules) / rule_count if rule_count else 1.0
    rule_validation = pass_rules / max(pass_rules + warn_rules, 1)
    return [
        _gate(
            "gate:verification_unit_coverage",
            "pass" if unit_count > 0 else "warn",
            1.0 if unit_count > 0 else 0.0,
            0.9,
            details={"unit_count": unit_count, "unit_type_counts": summary.get("unit_type_counts", {})},
        ),
        _gate(
            "gate:verification_value_confidence",
            "pass" if verified_ratio >= 0.8 else "warn",
            verified_ratio,
            0.8,
            details={
                "applicable_unit_count": summary.get("applicable_unit_count", 0),
                "unit_status_counts": summary.get("unit_status_counts", {}),
            },
        ),
        _gate(
            "gate:verification_conflict_ratio",
            "pass" if conflict_ratio <= 0.01 else "warn",
            1.0 - conflict_ratio,
            0.99,
            details={"conflict_ratio": conflict_ratio},
        ),
        _gate(
            "gate:verification_rule_evaluability",
            "pass" if rule_evaluable >= 0.8 else "warn",
            rule_evaluable,
            0.8,
            details={"rule_status_counts": rule_counts},
        ),
        _gate(
            "gate:verification_rule_validation",
            "pass" if warn_rules == 0 else "warn",
            rule_validation,
            0.8,
            details={"rule_status_counts": rule_counts},
        ),
    ]


def _gate(
    gate_id: str,
    status: str,
    score: float,
    threshold: float,
    *,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": gate_id,
        "status": status,
        "score": float(score),
        "threshold": float(threshold),
        "details": details or {},
    }
