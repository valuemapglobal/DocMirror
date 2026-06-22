# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""GA metrics integration for document structure readiness (STR-6-4).

Wires DFG structure metrics into the release gate evaluation framework.
Provides compute_structure_gate_metrics() for the TQG runner.
"""

from __future__ import annotations

from typing import Any


def compute_structure_gate_metrics(
    document_structure: dict[str, Any],
    *,
    page_count: int = 1,
) -> dict[str, Any]:
    """Compute structure gate metrics from a DFG document_structure dict.

    Args:
        document_structure: Output from build_document_structure().
        page_count: Total pages in the document.

    Returns:
        Metrics dict ready for GA release gate evaluation.
    """
    nodes = document_structure.get("nodes") or []
    edges = document_structure.get("edges") or []
    reading_flow = document_structure.get("reading_flow") or []
    outline = document_structure.get("outline") or []
    cross_page_flows = document_structure.get("cross_page_flows") or []
    relations = document_structure.get("relations") or []
    suppressed_noise = document_structure.get("suppressed_noise") or []

    # Node type coverage
    node_types: set[str] = set()
    for n in nodes:
        node_types.add(str(n.get("type", "")))

    # Edge type coverage
    edge_types: set[str] = set()
    for e in edges:
        edge_types.add(str(e.get("type", "")))

    # Reading flow node count
    main_flow_nodes = 0
    for rf in reading_flow:
        if rf.get("type") == "main_reading_order":
            main_flow_nodes = len(rf.get("node_ids", []))

    # Outline depth
    max_outline_depth = 1
    for sec in outline:
        level = int(sec.get("level", 1))
        if level > max_outline_depth:
            max_outline_depth = level

    return {
        "structure_version": document_structure.get("version", 1),
        "structure_profile": document_structure.get("profile", "legacy"),
        # Reading order
        "reading_order_coverage": 1.0 if reading_flow else 0.0,
        "main_flow_node_count": main_flow_nodes,
        "edge_count": len(edges),
        # Noise
        "noise_nodes_suppressed": len(suppressed_noise),
        "noise_node_types": sorted(set(n.get("type", "") for n in suppressed_noise)),
        # Section tree
        "outline_depth": max_outline_depth,
        "outline_section_count": len(outline),
        "outline_has_hierarchy": any(
            (s.get("children") or s.get("child_ids")) for s in outline
        ),
        # Cross-page
        "cross_page_flow_count": len(cross_page_flows),
        "cross_page_paragraph_count": sum(
            1 for f in cross_page_flows if f.get("type") == "cross_page_paragraph"
        ),
        "cross_page_table_count": sum(
            1 for f in cross_page_flows if f.get("type") == "cross_page_table"
        ),
        # Relations
        "relation_count": len(relations),
        "relation_types": sorted(set(r.get("type", "") for r in relations)),
        # Node coverage
        "node_count": len(nodes),
        "node_types": sorted(node_types),
        "node_type_coverage": len(node_types),
        "edge_types": sorted(edge_types),
        "edge_type_coverage": len(edge_types),
        # Overall readiness
        "structure_readiness_score": _compute_readiness_score(
            nodes=nodes,
            reading_flow=reading_flow,
            outline=outline,
            cross_page_flows=cross_page_flows,
            relations=relations,
            suppressed_noise=suppressed_noise,
        ),
    }


def _compute_readiness_score(
    *,
    nodes: list[dict[str, Any]],
    reading_flow: list[dict[str, Any]],
    outline: list[dict[str, Any]],
    cross_page_flows: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    suppressed_noise: list[dict[str, Any]],
) -> float:
    """Compute a weighted structure readiness score (0.0 to 1.0).

    P0 weight distribution:
      - Reading flow exists: 30%
      - Nodes present: 20%
      - Noise suppression active: 15%
      - Outline hierarchy: 15%
      - Cross-page flows: 10%
      - Relations: 10%
    """
    score = 0.0

    if reading_flow:
        score += 0.30
    if nodes:
        score += 0.20
    if suppressed_noise:
        score += 0.15
    if outline:
        score += 0.15
    if cross_page_flows:
        score += 0.10
    if relations:
        score += 0.10

    return min(1.0, score)


def evaluate_structure_gate(
    metrics: dict[str, Any],
    *,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate GA structure gate against thresholds.

    Args:
        metrics: Output from compute_structure_gate_metrics().
        thresholds: Gate thresholds dict. Defaults to GA 1.0 P0 minimums.

    Returns:
        Gate evaluation result with pass/fail, checks, and failures list.
    """
    t = thresholds or {}
    gate_checks: dict[str, bool] = {}
    failures: list[str] = []

    def _check(key: str, value: Any, threshold: Any, label: str) -> None:
        ok = value >= threshold if isinstance(value, (int, float)) else bool(value)
        gate_checks[label] = ok
        if not ok:
            failures.append(f"{label}: {value} < {threshold}")

    min_reading_flow = t.get("min_reading_flow_coverage", 0.5)
    _check("reading_order_coverage", metrics.get("reading_order_coverage", 0), min_reading_flow, "Reading flow exists")

    min_nodes = t.get("min_nodes", 1)
    _check("node_count", metrics.get("node_count", 0), min_nodes, "DFG nodes present")

    min_outline = t.get("min_outline_nodes", 1)
    outline_count = metrics.get("outline_section_count", 0)
    gate_checks["Outline sections"] = outline_count >= min_outline
    if outline_count < min_outline:
        failures.append(f"Outline sections: {outline_count} < {min_outline}")

    if t.get("require_noise_suppression", False):
        has_noise = metrics.get("noise_nodes_suppressed", 0) > 0
        gate_checks["Noise suppression"] = has_noise
        if not has_noise:
            failures.append("Noise suppression: no noise detected/suppressed")

    min_structure_score = t.get("min_structure_readiness", 0.5)
    readiness = metrics.get("structure_readiness_score", 0)
    gate_checks["Structure readiness score"] = readiness >= min_structure_score
    if readiness < min_structure_score:
        failures.append(f"Structure readiness: {readiness:.2f} < {min_structure_score}")

    return {
        "passed": len(failures) == 0,
        "checks": gate_checks,
        "failures": failures,
        "readiness_score": metrics.get("structure_readiness_score", 0),
    }


__all__ = [
    "compute_structure_gate_metrics",
    "evaluate_structure_gate",
]
