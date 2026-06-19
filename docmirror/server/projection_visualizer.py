# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""DBT-style projection graph visualization helpers."""

from __future__ import annotations

from typing import Any

from docmirror.server.projection_dag import ProjectionDAG


def projection_dag_to_json(dag: ProjectionDAG) -> dict[str, Any]:
    """Return a stable JSON-like graph representation."""
    return {
        "nodes": [
            {
                "name": node.name,
                "depends_on": list(node.depends_on),
                "description": node.description,
            }
            for node in sorted(dag.nodes.values(), key=lambda item: item.name)
        ],
        "order": list(dag.topological_order()),
    }


def projection_dag_to_mermaid(dag: ProjectionDAG) -> str:
    """Render a Mermaid graph suitable for docs/debug output."""
    lines = ["flowchart TD"]
    for node in sorted(dag.nodes.values(), key=lambda item: item.name):
        label = node.description or node.name
        lines.append(f'  {node.name}["{label}"]')
        for dep in node.depends_on:
            lines.append(f"  {dep} --> {node.name}")
    return "\n".join(lines)


__all__ = [
    "projection_dag_to_json",
    "projection_dag_to_mermaid",
]
