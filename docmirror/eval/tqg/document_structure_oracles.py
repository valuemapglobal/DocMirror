# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""DocumentStructure TQG oracle — v2 with DFG tests.

GA 1.0 STR-6-2: Extended to test DFG v2 fields:
  - nodes, edges, reading_flow, cross_page_flows, relations
  - structure_node_refs on chunks
  - node type and edge type coverage
"""

from __future__ import annotations

from typing import Any

from docmirror.eval.tqg.report import GateReport
from docmirror.models.mirror.document_structure import build_document_structure


def run_document_structure_oracle(
    result: Any,
    spec: dict[str, Any],
    *,
    case_id: str = "",
    track: str = "",
    tier: str = "",
) -> GateReport:
    report = GateReport(case_id=case_id, track=track, tier=tier)
    structure = _extract_document_structure(result)
    outline = structure.get("outline") or []
    flows = structure.get("flows") or []
    suppressed_noise = structure.get("suppressed_noise") or []
    report.metrics["outline_nodes"] = len(outline)
    report.metrics["flows"] = len(flows)
    report.metrics["suppressed_noise"] = len(suppressed_noise)

    # ── DFG v2 metrics (STR-6-2) ──────────────────────────────────────────
    nodes = structure.get("nodes") or []
    edges = structure.get("edges") or []
    reading_flow = structure.get("reading_flow") or []
    cross_page_flows = structure.get("cross_page_flows") or []
    relations = structure.get("relations") or []
    dfg_version = structure.get("version", 1)

    report.metrics["dfg_version"] = dfg_version
    report.metrics["dfg_node_count"] = len(nodes)
    report.metrics["dfg_edge_count"] = len(edges)
    report.metrics["dfg_reading_flow_count"] = len(reading_flow)
    report.metrics["dfg_cross_page_flow_count"] = len(cross_page_flows)
    report.metrics["dfg_relation_count"] = len(relations)

    # DFG node type coverage
    node_types: set[str] = set()
    for n in nodes:
        node_types.add(str(n.get("type", "")))
    report.metrics["dfg_node_type_count"] = len(node_types)

    # DFG edge type coverage
    edge_types: set[str] = set()
    for e in edges:
        edge_types.add(str(e.get("type", "")))
    report.metrics["dfg_edge_type_count"] = len(edge_types)

    # DFG schema gate
    ok_schema = dfg_version >= 2 if "structure_v2" in str(structure.get("profile", "")) else dfg_version >= 1
    report.checks["dfg_schema_version"] = ok_schema
    if not ok_schema:
        report.passed = False
        report.failures.append(f"DFG schema version {dfg_version} < expected")

    # DFG node count gate
    min_nodes = spec.get("min_dfg_nodes")
    if min_nodes is not None:
        ok = len(nodes) >= int(min_nodes)
        report.checks["min_dfg_nodes"] = ok
        if not ok:
            report.passed = False
            report.failures.append(f"DFG nodes {len(nodes)} < {min_nodes}")

    # DFG reading_flow gate
    if spec.get("require_reading_flow"):
        ok = len(reading_flow) > 0
        report.checks["require_reading_flow"] = ok
        if not ok:
            report.passed = False
            report.failures.append("No reading_flow found in DFG")

    # DFG node type gate
    required_node_types = set(spec.get("require_dfg_node_types") or [])
    if required_node_types:
        missing = required_node_types - node_types
        ok = not missing
        report.checks["require_dfg_node_types"] = ok
        if not ok:
            report.passed = False
            report.failures.append(f"Missing DFG node types {sorted(missing)}")

    # DFG relation gate
    required_relation_types = set(spec.get("require_relation_types") or [])
    if required_relation_types:
        actual_rel_types = {str(r.get("type", "")) for r in relations}
        missing = required_relation_types - actual_rel_types
        ok = not missing
        report.checks["require_relation_types"] = ok
        if not ok:
            report.passed = False
            report.failures.append(f"Missing relation types {sorted(missing)}")

    min_outline = spec.get("min_outline_nodes")
    if min_outline is not None:
        ok = len(outline) >= int(min_outline)
        report.checks["min_outline_nodes"] = ok
        if not ok:
            report.passed = False
            report.failures.append(f"outline nodes {len(outline)} < {min_outline}")

    min_flows = spec.get("min_flows")
    if min_flows is not None:
        ok = len(flows) >= int(min_flows)
        report.checks["min_flows"] = ok
        if not ok:
            report.passed = False
            report.failures.append(f"flows {len(flows)} < {min_flows}")

    required_flow_types = set(spec.get("require_flow_types") or [])
    if required_flow_types:
        actual = {str(flow.get("type")) for flow in flows if isinstance(flow, dict)}
        missing = required_flow_types - actual
        ok = not missing
        report.checks["require_flow_types"] = ok
        if not ok:
            report.passed = False
            report.failures.append(f"missing flow types {sorted(missing)}")

    required_noise_types = set(spec.get("require_suppressed_noise_types") or [])
    if required_noise_types:
        actual_noise = {str(item.get("type")) for item in suppressed_noise if isinstance(item, dict)}
        missing = required_noise_types - actual_noise
        ok = not missing
        report.checks["require_suppressed_noise_types"] = ok
        if not ok:
            report.passed = False
            report.failures.append(f"missing suppressed noise types {sorted(missing)}")

    return report


def _extract_document_structure(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        document = ((result.get("data") or {}).get("document") or {}) if isinstance(result.get("data"), dict) else {}
        existing = document.get("document_structure")
        if isinstance(existing, dict):
            return existing
        mirror = result.get("mirror")
        if mirror is not None:
            return build_document_structure(mirror)
        return {"version": 1, "outline": [], "flows": [], "suppressed_noise": []}
    return build_document_structure(result)
