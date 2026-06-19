# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Small projection DAG engine for Architecture A outputs.

The current production projection path is intentionally simple, but this module
defines the durable dependency model: Mirror facts first, then semantic
projections that only read upstream outputs.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any


ProjectionBuildFn = Callable[[Mapping[str, Any]], Any]


@dataclass(frozen=True)
class ProjectionNode:
    """One projection step in the Architecture A dependency graph."""

    name: str
    depends_on: tuple[str, ...] = ()
    build: ProjectionBuildFn | None = None
    description: str = ""


@dataclass
class ProjectionDAG:
    """A tiny deterministic DAG runner with cycle/missing dependency checks."""

    nodes: dict[str, ProjectionNode] = field(default_factory=dict)

    def add(self, node: ProjectionNode) -> None:
        if node.name in self.nodes:
            raise ValueError(f"duplicate projection node: {node.name}")
        self.nodes[node.name] = node

    def topological_order(self) -> tuple[str, ...]:
        incoming: dict[str, int] = {name: 0 for name in self.nodes}
        outgoing: dict[str, list[str]] = defaultdict(list)
        for name, node in self.nodes.items():
            for dep in node.depends_on:
                if dep not in self.nodes:
                    raise ValueError(f"projection node {name!r} depends on missing node {dep!r}")
                incoming[name] += 1
                outgoing[dep].append(name)

        ready = deque(sorted(name for name, count in incoming.items() if count == 0))
        order: list[str] = []
        while ready:
            name = ready.popleft()
            order.append(name)
            for child in sorted(outgoing[name]):
                incoming[child] -= 1
                if incoming[child] == 0:
                    ready.append(child)
        if len(order) != len(self.nodes):
            raise ValueError("projection DAG contains a cycle")
        return tuple(order)

    def run(self, initial_context: Mapping[str, Any] | None = None) -> dict[str, Any]:
        outputs: dict[str, Any] = dict(initial_context or {})
        for name in self.topological_order():
            node = self.nodes[name]
            if node.build is not None:
                outputs[name] = node.build(outputs)
        return outputs


def architecture_a_projection_dag(editions: tuple[str, ...] = ("community", "enterprise", "finance")) -> ProjectionDAG:
    """Return the standard Architecture A dependency graph."""
    dag = ProjectionDAG()
    dag.add(ProjectionNode("mirror", description="Core ParseResult fact snapshot"))
    if "community" in editions or "enterprise" in editions or "finance" in editions:
        dag.add(ProjectionNode("community", depends_on=("mirror",), description="Community semantic baseline"))
    for edition in ("enterprise", "finance"):
        if edition in editions:
            dag.add(
                ProjectionNode(
                    edition,
                    depends_on=("mirror", "community"),
                    description=f"{edition} projection with explicit composition",
                )
            )
    return dag


__all__ = [
    "ProjectionDAG",
    "ProjectionNode",
    "architecture_a_projection_dag",
]
