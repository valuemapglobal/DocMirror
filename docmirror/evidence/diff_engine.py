# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Diff Engine (W4-02, W4-03).

Compares two canonicalized VisualEvidenceGraphs (base and candidate) and
produces a DiffReport with changed nodes, severity ratings, visual diff
overlay data, and a summary gate.

Usage::

    from docmirror.evidence.diff_engine import DiffReport, diff_graphs
    report = diff_graphs(base_canonical, candidate_canonical)
    print(report.to_dict())
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class DiffChange:
    """A single changed element between two parse runs."""

    id: str = ""
    kind: Literal[
        "node_added", "node_removed", "node_changed",
        "field_value_changed", "field_added", "field_removed",
        "confidence_changed", "bbox_changed",
        "edge_added", "edge_removed",
        "review_changed", "coverage_changed",
        "quality_decision_changed", "needs_review_added", "needs_review_removed",
    ] = "node_changed"
    severity: Literal["low", "medium", "high"] = "low"
    node_id: str = ""
    field_path: str = ""
    before: Any = None
    after: Any = None
    source_refs: list[str] = field(default_factory=list)
    visual_nodes: list[str] = field(default_factory=list)
    page: int = 0
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "severity": self.severity,
            "node_id": self.node_id,
            "field_path": self.field_path,
            "before": self.before,
            "after": self.after,
            "source_refs": self.source_refs,
            "visual_nodes": self.visual_nodes,
            "page": self.page,
            "message": self.message,
        }


@dataclass
class DiffReport:
    """GA 1.0 Diff Report -- run-to-run comparison artifact (W4)."""

    version: int = 1
    base_run: str = ""
    candidate_run: str = ""
    status: Literal["pass", "warning", "fail"] = "pass"
    summary: dict[str, int] = field(default_factory=lambda: {
        "node_added": 0, "node_removed": 0, "node_changed": 0,
        "field_value_changed": 0, "confidence_changed": 0, "bbox_changed": 0,
        "edge_added": 0, "edge_removed": 0,
        "quality_decision_changed": 0, "total_changes": 0,
    })
    changes: list[DiffChange] = field(default_factory=list)
    budgets: dict[str, Any] = field(default_factory=lambda: {
        "allowed_high_severity_changes": 0,
        "allowed_layout_iou_drop": 0.02,
    })
    diff_overlay: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "base_run": self.base_run,
            "candidate_run": self.candidate_run,
            "status": self.status,
            "summary": self.summary,
            "changes": [c.to_dict() for c in self.changes],
            "budgets": self.budgets,
            "diff_overlay": self.diff_overlay,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiffReport:
        report = cls(
            version=data.get("version", 1),
            base_run=data.get("base_run", ""),
            candidate_run=data.get("candidate_run", ""),
            status=data.get("status", "pass"),
            summary=data.get("summary", {}),
            budgets=data.get("budgets", {}),
            diff_overlay=data.get("diff_overlay", []),
        )
        for c in data.get("changes", []):
            report.changes.append(DiffChange(
                id=c.get("id", ""), kind=c.get("kind", "node_changed"),
                severity=c.get("severity", "low"),
                node_id=c.get("node_id", ""), field_path=c.get("field_path", ""),
                before=c.get("before"), after=c.get("after"),
                source_refs=c.get("source_refs", []),
                visual_nodes=c.get("visual_nodes", []),
                page=c.get("page", 0), message=c.get("message", ""),
            ))
        return report


def diff_graphs(
    base: dict[str, Any],
    candidate: dict[str, Any],
    *,
    base_run: str = "base",
    candidate_run: str = "candidate",
    budgets: dict[str, Any] | None = None,
) -> DiffReport:
    """Compare two canonicalized VisualEvidenceGraphs.

    Produces a DiffReport with changed nodes, severity ratings, visual diff
    overlay data, and a summary gate.
    """
    report = DiffReport(
        base_run=base_run,
        candidate_run=candidate_run,
        budgets=budgets or {
            "allowed_high_severity_changes": 0,
            "allowed_layout_iou_drop": 0.02,
        },
    )

    base_nodes = base.get("nodes", {})
    cand_nodes = candidate.get("nodes", {})
    base_edges = {(e.get("from", e.get("from_node", "")), e.get("to", e.get("to_node", ""))): e
                  for e in base.get("edges", [])}
    cand_edges = {(e.get("from", e.get("from_node", "")), e.get("to", e.get("to_node", ""))): e
                  for e in candidate.get("edges", [])}

    change_idx = 0

    # ── Nodes diff ──
    all_node_ids = set(base_nodes.keys()) | set(cand_nodes.keys())
    for nid in sorted(all_node_ids):
        base_n = base_nodes.get(nid)
        cand_n = cand_nodes.get(nid)

        if base_n is None and cand_n is not None:
            change_idx += 1
            report.changes.append(DiffChange(
                id=f"diff_{change_idx:04d}",
                kind="node_added",
                severity="low",
                node_id=nid,
                after=cand_n.get("label", ""),
                visual_nodes=[nid],
                page=cand_n.get("page", 0),
                message=f"Node {nid} added: {cand_n.get('label', '')}",
            ))
            report.summary["node_added"] += 1
            _add_diff_overlay(report, nid, cand_n, kind="node_added", severity="low")
            continue

        if base_n is not None and cand_n is None:
            change_idx += 1
            severity = "medium" if base_n.get("kind") in ("field", "table", "cell") else "low"
            report.changes.append(DiffChange(
                id=f"diff_{change_idx:04d}",
                kind="node_removed",
                severity=severity,
                node_id=nid,
                before=base_n.get("label", ""),
                visual_nodes=[nid],
                page=base_n.get("page", 0),
                message=f"Node {nid} removed: {base_n.get('label', '')}",
            ))
            report.summary["node_removed"] += 1
            _add_diff_overlay(report, nid, base_n, kind="node_removed", severity=severity)
            continue

        # Both exist -- compare fields
        changed = False
        for field in ("kind", "label", "value_preview", "raw_preview", "confidence",
                       "review", "page", "bbox", "source_refs", "field_path", "edition"):
            bv = base_n.get(field)
            cv = cand_n.get(field)
            if bv != cv:
                changed = True
                change_idx += 1

                if field == "confidence":
                    diff_kind = "confidence_changed"
                    sev = "high" if abs((bv or 0) - (cv or 0)) > 0.2 else "medium"
                    report.summary["confidence_changed"] += 1
                elif field == "bbox":
                    diff_kind = "bbox_changed"
                    sev = "medium"
                    report.summary["bbox_changed"] += 1
                elif field in ("value_preview", "raw_preview"):
                    diff_kind = "field_value_changed"
                    sev = "high"
                    report.summary["field_value_changed"] += 1
                elif field == "review":
                    diff_kind = "review_changed"
                    sev = "medium"
                else:
                    diff_kind = "node_changed"
                    sev = "low"
                    report.summary["node_changed"] += 1

                report.changes.append(DiffChange(
                    id=f"diff_{change_idx:04d}",
                    kind=diff_kind,
                    severity=sev,
                    node_id=nid,
                    field_path=base_n.get("field_path", "") or cand_n.get("field_path", ""),
                    before=f"{field}: {bv}",
                    after=f"{field}: {cv}",
                    source_refs=base_n.get("source_refs", []) or cand_n.get("source_refs", []),
                    visual_nodes=[nid],
                    page=base_n.get("page", 0),
                    message=f"Node {nid} {field} changed: {bv} -> {cv}",
                ))
                if field == "bbox":
                    _add_diff_overlay(report, nid, cand_n, kind="bbox_changed", severity=sev)

    # ── Edges diff ──
    base_edge_keys = set(base_edges.keys())
    cand_edge_keys = set(cand_edges.keys())
    for ek in sorted(cand_edge_keys - base_edge_keys):
        change_idx += 1
        e = cand_edges[ek]
        report.changes.append(DiffChange(
            id=f"diff_{change_idx:04d}",
            kind="edge_added",
            severity="low",
            node_id=f"{ek[0]} -> {ek[1]}",
            message=f"Edge {ek[0]} -> {ek[1]} added",
        ))
        report.summary["edge_added"] += 1
    for ek in sorted(base_edge_keys - cand_edge_keys):
        change_idx += 1
        e = base_edges[ek]
        report.changes.append(DiffChange(
            id=f"diff_{change_idx:04d}",
            kind="edge_removed",
            severity="low",
            node_id=f"{ek[0]} -> {ek[1]}",
            message=f"Edge {ek[0]} -> {ek[1]} removed",
        ))
        report.summary["edge_removed"] += 1

    # ── Quality decision diff ──
    base_qd = base.get("quality_decision") or {}
    cand_qd = candidate.get("quality_decision") or {}
    if base_qd.get("decision") != cand_qd.get("decision"):
        change_idx += 1
        report.changes.append(DiffChange(
            id=f"diff_{change_idx:04d}",
            kind="quality_decision_changed",
            severity="high",
            before=base_qd.get("decision", ""),
            after=cand_qd.get("decision", ""),
            message=f"Quality decision: {base_qd.get('decision')} -> {cand_qd.get('decision')}",
        ))
        report.summary["quality_decision_changed"] += 1

    # ── Compute summary and status ──
    report.summary["total_changes"] = len(report.changes)
    high_sev = sum(1 for c in report.changes if c.severity == "high")
    allowed = report.budgets.get("allowed_high_severity_changes", 0)
    if high_sev > allowed:
        report.status = "fail"
    elif report.summary["total_changes"] > 0:
        report.status = "warning"
    else:
        report.status = "pass"

    return report


def _add_diff_overlay(
    report: DiffReport,
    node_id: str,
    node: dict[str, Any],
    kind: str,
    severity: str,
) -> None:
    page = node.get("page", 0) or 0
    bbox = node.get("bbox")
    if not bbox or page <= 0:
        return
    stroke = "#8250df" if severity == "low" else "#d29922" if severity == "medium" else "#cf222e"
    report.diff_overlay.append({
        "node_id": node_id,
        "page": page,
        "bbox": bbox,
        "kind": kind,
        "severity": severity,
        "style": {"stroke": stroke, "strokeWidth": 2, "fill": "rgba(130,80,223,0.10)"},
        "label": f"{kind}: {node.get('label', '')}"[:60],
        "tooltip": f"diff {kind} severity={severity}",
    })


__all__ = ["DiffChange", "DiffReport", "diff_graphs"]
