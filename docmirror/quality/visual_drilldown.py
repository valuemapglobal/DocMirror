# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Visual Debug Drilldown — QTC W5-04.

Bridges quality metrics and visual debug overlays by providing a drilldown
path from metric → page → field → bbox → evidence. This enables users to
click on a low-quality metric and navigate to the exact visual location
where the problem occurred.

Design reference: docs/design/GA1.0/08_accuracy_trust_ga_gap_closure_plan.md W5-04
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from docmirror.quality.observation import (
    FidelityLayer,
    QualityObservationEvent,
)

# ── Drilldown Target ────────────────────────────────────────────────────────


@dataclass
class DrilldownTarget:
    """A visual drilldown target mapping a metric failure to a visual location.

    Each target represents a specific page / field / bbox that can be
    visually highlighted in visual_debug.html or a debug viewer.
    """

    observation_id: str = ""
    fixture_id: str = ""
    domain: str = ""
    metric_name: str = ""  # e.g. "amount_accuracy", "reading_order_accuracy"
    metric_layer: str = ""  # text | layout | business | audit
    page_number: int | None = None
    field_path: str = ""  # e.g. "account_number", "total_amount"
    bbox: list[float] | None = None  # [x0, y0, x1, y1] in page_pixels
    current_value: float = 0.0
    target_value: float = 0.0
    confidence: float = 0.0
    severity: str = "warning"  # info | warning | error | critical
    evidence_refs: list[str] = field(default_factory=list)
    suggestion: str = ""


# ── Drilldown Engine ─────────────────────────────────────────────────────────


@dataclass
class DrilldownSession:
    """Collects drilldown targets from quality observation events.

    Each observation can produce multiple drilldown targets — one per
    failing metric, mapping to the specific page/field/bbox evidence.
    """

    targets: list[DrilldownTarget] = field(default_factory=list)

    def add_from_observation(self, event: QualityObservationEvent) -> None:
        """Scan a QualityObservationEvent and produce drilldown targets for failing metrics."""
        layers: list[tuple[str, FidelityLayer]] = [
            ("text", event.fidelity.text),
            ("layout", event.fidelity.layout),
            ("business", event.fidelity.business),
            ("audit", event.fidelity.audit),
        ]

        for layer_name, layer in layers:
            for metric_name, observed_val in layer.metrics.items():
                if observed_val <= 0:
                    continue  # not measured / irrelevant

                target_val = _get_target_for_metric(metric_name)
                if target_val is None:
                    continue

                status = _metric_status(observed_val, target_val, metric_name)
                if status == "pass":
                    continue

                # Extract page/bbox from evidence refs if available
                page_num = _extract_page_number(layer)
                bbox = _extract_bbox(layer)
                field_path = _extract_field_path(metric_name)

                self.targets.append(
                    DrilldownTarget(
                        observation_id=event.observation_id,
                        fixture_id=event.input.fixture_id,
                        domain=event.input.domain,
                        metric_name=metric_name,
                        metric_layer=layer_name,
                        page_number=page_num,
                        field_path=field_path,
                        bbox=bbox,
                        current_value=observed_val,
                        target_value=target_val,
                        confidence=observed_val / target_val if target_val > 0 else 0.0,
                        severity=_severity_from_gap(observed_val, target_val),
                        evidence_refs=list(layer.evidence_refs),
                        suggestion=_suggest_remediation(metric_name, layer_name),
                    )
                )

        # Also add page-level drilldown for failures
        for page_outcome in event.failure.partial_pages:
            if page_outcome.status != "success":
                self.targets.append(
                    DrilldownTarget(
                        observation_id=event.observation_id,
                        fixture_id=event.input.fixture_id,
                        domain=event.input.domain,
                        metric_name="page_outcome",
                        metric_layer="layout",
                        page_number=page_outcome.page,
                        severity="error" if page_outcome.status == "failure" else "warning",
                        suggestion=f"Page {page_outcome.page}: {page_outcome.error_code or 'unknown error'}",
                    )
                )

    def by_page(self, page_number: int) -> list[DrilldownTarget]:
        """Return all drilldown targets for a specific page."""
        return [t for t in self.targets if t.page_number == page_number]

    def by_domain(self, domain: str) -> list[DrilldownTarget]:
        """Return all drilldown targets for a specific domain."""
        return [t for t in self.targets if t.domain == domain]

    def by_layer(self, layer: str) -> list[DrilldownTarget]:
        """Return all drilldown targets for a specific fidelity layer."""
        return [t for t in self.targets if t.metric_layer == layer]

    def by_severity(self, severity: str) -> list[DrilldownTarget]:
        """Return all drilldown targets at a given severity level."""
        return [t for t in self.targets if t.severity == severity]

    def pages_with_issues(self) -> set[int]:
        """Return set of all page numbers with drilldown targets."""
        return {t.page_number for t in self.targets if t.page_number is not None}

    def to_overlay_dict(self) -> dict[str, Any]:
        """Export as overlay dict suitable for visual_debug.html consumption.

        Grouped by page for overlay rendering.
        """
        overlays_by_page: dict[int, list[dict[str, Any]]] = {}
        for target in self.targets:
            if target.page_number is None:
                continue
            if target.page_number not in overlays_by_page:
                overlays_by_page[target.page_number] = []
            overlays_by_page[target.page_number].append(
                {
                    "metric": target.metric_name,
                    "layer": target.metric_layer,
                    "field_path": target.field_path,
                    "bbox": target.bbox,
                    "current_value": target.current_value,
                    "target_value": target.target_value,
                    "severity": target.severity,
                    "suggestion": target.suggestion,
                    "evidence_refs": target.evidence_refs,
                }
            )

        return {
            "drilldown_version": 1,
            "total_targets": len(self.targets),
            "pages_with_issues": sorted(self.pages_with_issues()),
            "by_page": {str(k): v for k, v in sorted(overlays_by_page.items())},
            "by_layer": {layer: len(self.by_layer(layer)) for layer in ("text", "layout", "business", "audit")},
        }

    def to_summary_dict(self) -> dict[str, Any]:
        """Export summary for quality reports."""
        return {
            "total_drilldown_targets": len(self.targets),
            "pages_with_issues": sorted(self.pages_with_issues()),
            "targets_by_layer": {layer: len(self.by_layer(layer)) for layer in ("text", "layout", "business", "audit")},
            "targets_by_severity": {
                sev: len(self.by_severity(sev)) for sev in ("info", "warning", "error", "critical")
            },
            "top_failing_metrics": _top_failing_metrics(self.targets, limit=10),
        }


# ── Helpers ──────────────────────────────────────────────────────────────────


# Metrics where lower observed value is better (max direction)
_MAX_DIRECTION_METRICS: set[str] = {
    "silent_failure_rate",
    "cer",
    "garbled_ratio",
    "noise_leakage_rate",
    "no_evidence_auto_accept_rate",
}

# Metric targets for drilldown (mirrors ga_metrics.py targets)
_METRIC_TARGETS: dict[str, float] = {
    "silent_failure_rate": 0.0,
    "schema_validation_pass_rate": 0.99,
    "evidence_coverage_for_key_fields": 0.95,
    "page_level_partial_retention": 1.0,
    "error_envelope_coverage": 1.0,
    "markdown_generation_success": 0.99,
    "mirror_json_generation_success": 0.99,
    "cpu_only_parse_availability": 1.0,
    "license_missing_does_not_affect_mirror": 1.0,
    "transaction_row_count_fidelity": 0.98,
    "amount_field_accuracy": 0.99,
    "date_field_accuracy": 0.98,
    "account_or_serial_evidence_coverage": 0.95,
    "needs_review_recall_for_low_confidence_fields": 0.95,
    "cer": 0.05,  # max direction
    "char_preservation_rate": 0.95,
    "garbled_ratio": 0.01,  # max direction
    "ocr_confidence_avg": 0.85,
    "reading_order_accuracy": 0.98,
    "bbox_coverage": 0.95,
    "table_structure_score": 0.90,
    "cross_page_continuity": 0.95,
    "noise_leakage_rate": 0.01,  # max direction
    "field_accuracy": 0.99,
    "record_count_fidelity": 0.98,
    "amount_accuracy": 0.99,  # duplicate name, used as alias
    "date_accuracy": 0.98,  # duplicate name, used as alias
    "account_serial_accuracy": 0.95,
    "source_refs_coverage": 0.95,
    "bbox_evidence_coverage": 0.95,
    "evidence_completeness": 1.0,
    "needs_review_recall": 0.95,
    "no_evidence_auto_accept_rate": 0.0,  # max direction
}


def _get_target_for_metric(metric_name: str) -> float | None:
    """Get the GA target value for a metric name."""
    # Try exact match
    if metric_name in _METRIC_TARGETS:
        return _METRIC_TARGETS[metric_name]
    # Try fuzzy match
    for key, val in _METRIC_TARGETS.items():
        if key in metric_name or metric_name in key:
            return val
    return None


def _metric_status(observed: float, target: float, metric_name: str = "") -> str:
    """Determine if a metric passes or fails based on its direction.

    For max-direction metrics (lower is better, e.g., CER, error rates),
    observed <= target means pass. For all others (min direction),
    observed >= target means pass.
    """
    if metric_name and any(m in metric_name for m in _MAX_DIRECTION_METRICS):
        return "pass" if observed <= target else "fail"
    return "pass" if observed >= target else "fail"


def _extract_page_number(layer: FidelityLayer) -> int | None:
    """Extract page number from a fidelity layer's evidence refs."""
    for ref in layer.evidence_refs:
        if ref.startswith("page:"):
            try:
                return int(ref.split(":")[1])
            except (ValueError, IndexError):
                pass
    return None


def _extract_bbox(layer: FidelityLayer) -> list[float] | None:
    """Extract bbox from a fidelity layer's evidence refs."""
    for ref in layer.evidence_refs:
        if ref.startswith("bbox:") and len(ref.split(":")) >= 5:
            try:
                parts = ref.split(":")[1:]
                return [float(p) for p in parts[:4]]
            except (ValueError, IndexError):
                pass
    return None


def _extract_field_path(metric_name: str) -> str:
    """Derive a field path from the metric name."""
    field_mapping = {
        "amount": "amount",
        "date": "transaction_date",
        "account": "account_number",
        "serial": "serial_number",
        "field_accuracy": "fields",
        "record_count": "records",
        "reading_order": "reading_order",
        "bbox": "bbox",
        "table_structure": "tables",
        "cer": "text",
        "char_preservation": "text",
        "garbled_ratio": "text",
        "ocr_confidence": "ocr",
        "noise_leakage": "header_footer",
    }
    for key, path in field_mapping.items():
        if key in metric_name.lower():
            return path
    return metric_name


def _severity_from_gap(observed: float, target: float) -> str:
    """Classify severity based on the gap between observed and target."""
    if target == 0:
        return "critical" if observed > 0 else "pass"
    gap_pct = (target - observed) / target
    if gap_pct <= 0.01:
        return "info"
    elif gap_pct <= 0.05:
        return "warning"
    elif gap_pct <= 0.20:
        return "error"
    else:
        return "critical"


def _suggest_remediation(metric_name: str, layer: str) -> str:
    """Generate a remediation suggestion for a failing metric."""
    suggestions = {
        "cer": "Re-scan with higher DPI or better OCR engine",
        "char_preservation_rate": "Check for encoding issues or font embedding problems",
        "garbled_ratio": "Enable garbled character filtering and re-parse",
        "reading_order_accuracy": "Enable VLM-assisted layout analysis",
        "bbox_coverage": "Ensure the document has extractable text positions",
        "table_structure_score": "Use HTML table mode for complex tables",
        "cross_page_continuity": "Check DocumentStructure merge logic",
        "noise_leakage_rate": "Tune header/footer noise filter thresholds",
        "field_accuracy": "Review plugin field extraction rules for this domain",
        "amount_accuracy": "Check amount normalization logic for currency/format",
        "date_accuracy": "Check date format detection for this locale",
        "evidence_coverage": "Verify plugin source_refs declarations",
        "needs_review_recall": "Adjust confidence thresholds for low-confidence flagging",
    }
    for key, suggestion in suggestions.items():
        if key in metric_name.lower():
            return suggestion
    return f"Review {layer} fidelity layer configuration"


def _top_failing_metrics(targets: list[DrilldownTarget], limit: int = 10) -> list[dict[str, Any]]:
    """Return the top failing metrics sorted by severity."""

    severity_order = {"critical": 0, "error": 1, "warning": 2, "info": 3}
    sorted_targets = sorted(
        targets,
        key=lambda t: (
            severity_order.get(t.severity, 99),
            t.target_value - t.current_value if t.target_value > 0 else 0,
        ),
        reverse=True,
    )

    seen: set[str] = set()
    top: list[dict[str, Any]] = []
    for t in sorted_targets:
        key = f"{t.metric_name}:{t.domain}"
        if key not in seen:
            seen.add(key)
            top.append(
                {
                    "metric": t.metric_name,
                    "domain": t.domain,
                    "fixture_id": t.fixture_id,
                    "page": t.page_number,
                    "current": t.current_value,
                    "target": t.target_value,
                    "gap": t.target_value - t.current_value,
                    "severity": t.severity,
                    "suggestion": t.suggestion,
                }
            )
            if len(top) >= limit:
                break
    return top
