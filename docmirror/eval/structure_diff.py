# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Visual diff artifact for document structure before/after comparison (STR-6-3).

Generates a diff report comparing legacy v1 structure output with DFG v2 output,
showing improvements in:
  - reading order coverage
  - noise suppression
  - outline hierarchy
  - cross-page continuity detection
  - image/formula node retention
"""

from __future__ import annotations

from typing import Any


def generate_structure_diff(
    v1_structure: dict[str, Any],
    v2_structure: dict[str, Any],
    *,
    case_id: str = "",
) -> dict[str, Any]:
    """Generate a visualizable diff between legacy v1 and DFG v2 structure.

    Args:
        v1_structure: Legacy document_structure dict (profile="legacy").
        v2_structure: DFG v2 document_structure dict (profile="ga_full").
        case_id: Optional identifier for the diff case.

    Returns:
        Diff report dict with sections for each structure category.
    """
    diff: dict[str, Any] = {
        "case_id": case_id,
        "v1_version": v1_structure.get("version", 1),
        "v2_version": v2_structure.get("version", 1),
        "sections": {},
    }

    # 1. Outline diff
    v1_outline = v1_structure.get("outline") or []
    v2_outline = v2_structure.get("outline") or []
    diff["sections"]["outline"] = {
        "v1_count": len(v1_outline),
        "v2_count": len(v2_outline),
        "delta": len(v2_outline) - len(v1_outline),
        "v2_has_children": any(bool(s.get("children") or s.get("child_ids")) for s in v2_outline),
    }

    # 2. Flows diff
    v1_flows = v1_structure.get("flows") or []
    v2_flows = v2_structure.get("cross_page_flows") or []
    v1_flow_types = {str(f.get("type", "")) for f in v1_flows}
    v2_flow_types = {str(f.get("type", "")) for f in v2_flows}
    diff["sections"]["flows"] = {
        "v1_count": len(v1_flows),
        "v2_count": len(v2_flows),
        "v1_types": sorted(v1_flow_types),
        "v2_types": sorted(v2_flow_types),
        "new_types": sorted(v2_flow_types - v1_flow_types),
    }

    # 3. Nodes diff
    v2_nodes = v2_structure.get("nodes") or []
    node_type_counts: dict[str, int] = {}
    for n in v2_nodes:
        nt = str(n.get("type", "unknown"))
        node_type_counts[nt] = node_type_counts.get(nt, 0) + 1
    diff["sections"]["nodes"] = {
        "v2_count": len(v2_nodes),
        "type_counts": node_type_counts,
    }

    # 4. Edges diff
    v2_edges = v2_structure.get("edges") or []
    edge_type_counts: dict[str, int] = {}
    for e in v2_edges:
        et = str(e.get("type", "unknown"))
        edge_type_counts[et] = edge_type_counts.get(et, 0) + 1
    diff["sections"]["edges"] = {
        "v2_count": len(v2_edges),
        "type_counts": edge_type_counts,
    }

    # 5. Reading flow diff
    v2_reading_flow = v2_structure.get("reading_flow") or []
    reading_flow_summary = []
    for rf in v2_reading_flow:
        reading_flow_summary.append({
            "flow_id": rf.get("flow_id", ""),
            "node_count": len(rf.get("node_ids", [])),
            "excluded_count": len(rf.get("excluded_node_ids", [])),
            "source_pages": rf.get("source_pages", []),
        })
    diff["sections"]["reading_flow"] = {
        "v2_count": len(v2_reading_flow),
        "details": reading_flow_summary,
    }

    # 6. Relations diff
    v2_relations = v2_structure.get("relations") or []
    rel_type_counts: dict[str, int] = {}
    for r in v2_relations:
        rt = str(r.get("type", "unknown"))
        rel_type_counts[rt] = rel_type_counts.get(rt, 0) + 1
    diff["sections"]["relations"] = {
        "v2_count": len(v2_relations),
        "type_counts": rel_type_counts,
    }

    # 7. Noise diff
    v1_noise = v1_structure.get("suppressed_noise") or []
    v2_noise = v2_structure.get("suppressed_noise") or []
    v1_noise_types = {str(n.get("type", "")) for n in v1_noise}
    v2_noise_types = {str(n.get("type", "")) for n in v2_noise}
    diff["sections"]["noise"] = {
        "v1_count": len(v1_noise),
        "v2_count": len(v2_noise),
        "v1_types": sorted(v1_noise_types),
        "v2_types": sorted(v2_noise_types),
        "new_types": sorted(v2_noise_types - v1_noise_types),
    }

    # Summary improvement metrics
    diff["summary"] = {
        "has_reading_flow": len(v2_reading_flow) > 0,
        "has_nodes": len(v2_nodes) > 0,
        "has_edges": len(v2_edges) > 0,
        "has_relations": len(v2_relations) > 0,
        "outline_improvement": len(v2_outline) - len(v1_outline),
        "flow_type_improvement": len(v2_flow_types - v1_flow_types),
        "noise_detection_improvement": len(v2_noise_types - v1_noise_types),
    }

    return diff


def format_diff_report(diff: dict[str, Any]) -> str:
    """Format a structure diff as a human-readable Markdown report."""
    lines: list[str] = []
    lines.append(f"# Structure Diff Report: {diff.get('case_id', 'Unnamed')}")
    lines.append("")
    lines.append(f"**V{diff['v1_version']} → V{diff['v2_version']}**")
    lines.append("")

    summary = diff.get("summary", {})
    lines.append("## Summary")
    lines.append("")
    for key, value in summary.items():
        icon = "✅" if value else "❌"
        lines.append(f"- {icon} **{key}**: {value}")
    lines.append("")

    for section_name, section_data in (diff.get("sections") or {}).items():
        lines.append(f"## {section_name.replace('_', ' ').title()}")
        lines.append("")
        for key, value in section_data.items():
            if isinstance(value, dict):
                lines.append(f"- **{key}**:")
                for sub_k, sub_v in value.items():
                    lines.append(f"  - {sub_k}: {sub_v}")
            elif isinstance(value, list):
                lines.append(f"- **{key}**: {value}")
            else:
                lines.append(f"- **{key}**: {value}")
        lines.append("")

    return "\n".join(lines)


__all__ = ["generate_structure_diff", "format_diff_report"]
