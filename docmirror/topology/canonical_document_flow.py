# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Build the canonical, source-complete reading flow stored on ParseResult."""

from __future__ import annotations

from typing import Any

from docmirror.models.mirror.document_flow import (
    DocumentFlowGraph,
    ReadingFlow,
    StructureEdge,
    StructureNode,
)


def build_canonical_document_flow(pages: list[Any]) -> DocumentFlowGraph:
    nodes: list[StructureNode] = []
    edges: list[StructureEdge] = []
    flow_ids: list[str] = []
    global_order = 0
    previous: str | None = None

    for page in pages:
        page_number = int(getattr(page, "page_number", 0) or 0)
        items: list[tuple[tuple[float, float, float, int], str, Any]] = []
        sequence = 0
        for kind, values in (
            ("text", getattr(page, "texts", []) or []),
            ("key_value", getattr(page, "key_values", []) or []),
            ("table", getattr(page, "tables", []) or []),
        ):
            for value in values:
                bbox = getattr(value, "bbox", None)
                order = float(getattr(value, "reading_order", 0) or 0)
                top = float(bbox[1]) if isinstance(bbox, list | tuple) and len(bbox) >= 2 else 1_000_000.0
                left = float(bbox[0]) if isinstance(bbox, list | tuple) and len(bbox) >= 1 else 1_000_000.0
                items.append(((order, top, left, sequence), kind, value))
                sequence += 1

        for _, kind, value in sorted(items, key=lambda item: item[0]):
            global_order += 1
            node = _node(page_number, global_order, kind, value)
            nodes.append(node)
            flow_ids.append(node.node_id)
            if previous is not None:
                edges.append(
                    StructureEdge(
                        edge_id=f"edge:{previous}:{node.node_id}",
                        type="reading_next",
                        from_node=previous,
                        to_node=node.node_id,
                        confidence=1.0,
                        policy="canonical_geometry_order",
                    )
                )
            previous = node.node_id

    pages_in_flow = sorted({node.page for node in nodes})
    return DocumentFlowGraph(
        profile="source_complete",
        nodes=nodes,
        edges=edges,
        reading_flow=[
            ReadingFlow(
                flow_id="flow:source_complete",
                type="main_reading_order",
                node_ids=flow_ids,
                source_pages=pages_in_flow,
                confidence=1.0 if nodes else 0.0,
                profile="source_complete",
                policy="canonical_geometry_order",
            )
        ],
        quality={
            "node_count": len(nodes),
            "edge_count": len(edges),
            "complete": bool(nodes),
        },
    )


def _node(page_number: int, order: int, kind: str, value: Any) -> StructureNode:
    bbox = list(getattr(value, "bbox", None) or []) or None
    evidence = list(getattr(value, "evidence_ids", None) or [])
    if kind == "table":
        table_id = str(getattr(value, "table_id", "") or f"table:{order}")
        return StructureNode(
            node_id=f"node:p{page_number}:table:{table_id}",
            type="physical_table",
            role="body",
            page=page_number,
            bbox=bbox,
            fact_refs=[table_id],
            evidence_refs=evidence,
            reading_order=order,
            confidence=float(getattr(value, "confidence", 1.0) or 0.0),
            metadata={"table_id": table_id},
        )
    if kind == "key_value":
        key = str(getattr(value, "key", "") or "")
        val = str(getattr(value, "value", "") or "")
        return StructureNode(
            node_id=f"node:p{page_number}:kv:{order}",
            type="paragraph",
            role="key_value",
            page=page_number,
            bbox=bbox,
            text=f"{key}: {val}".strip(": "),
            evidence_refs=evidence,
            reading_order=order,
            confidence=float(getattr(value, "confidence", 1.0) or 0.0),
            metadata={"key": key, "value": val},
        )

    level = str(getattr(getattr(value, "level", None), "value", getattr(value, "level", "")) or "")
    role = str(getattr(value, "role", "body") or "body")
    node_type = "heading" if level in {"title", "h1", "h2", "h3"} else ("footer" if role == "footer" else "paragraph")
    return StructureNode(
        node_id=f"node:p{page_number}:text:{order}",
        type=node_type,
        role=role,
        page=page_number,
        bbox=bbox,
        text=str(getattr(value, "content", "") or ""),
        evidence_refs=evidence,
        reading_order=order,
        confidence=float(getattr(value, "confidence", 1.0) or 0.0),
        metadata={"level": level},
    )


__all__ = ["build_canonical_document_flow"]
