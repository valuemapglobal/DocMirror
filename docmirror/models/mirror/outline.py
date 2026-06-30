# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""OutlineBuilder — build section tree from heading nodes.

Builds a hierarchical outline with secion nodes, parent-child relationships,
and content_node_ids assigned to each section.
"""

from __future__ import annotations

from typing import Any


def build_outline(
    nodes: list[dict[str, Any]],
    *,
    pages: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build a hierarchical section outline from DFG heading nodes.

    Args:
        nodes: DFG StructureNode dicts.
        pages: Optional page-level data for fallback section detection.

    Returns:
        List of section dicts with node_id, title, level, child_ids, content_node_ids.
    """
    sections: list[dict[str, Any]] = []

    # Extract heading nodes
    heading_nodes = [n for n in nodes if n.get("type") == "heading"]
    if not heading_nodes:
        # Fallback: create flat sections from page-level heading texts
        if pages:
            for page in pages:
                page_no = int(page.get("page_number") or 1)
                for text in page.get("texts") or []:
                    if not isinstance(text, dict):
                        continue
                    level = str(text.get("level") or "").lower()
                    content = str(text.get("content") or "").strip()
                    if content and level in ("title", "h1", "h2", "h3"):
                        sections.append(
                            {
                                "node_id": f"sec:p{page_no}_h{len(sections)}",
                                "type": "section",
                                "title": content,
                                "level": {"title": 1, "h1": 1, "h2": 2, "h3": 3}.get(level, 1),
                                "page_start": page_no,
                                "page_end": page_no,
                                "child_ids": [],
                                "content_node_ids": [],
                                "confidence": float(text.get("confidence", 1.0) or 1.0),
                            }
                        )
        return sections

    heading_nodes_sorted = sorted(heading_nodes, key=lambda n: n.get("reading_order", 0))

    # Build section stack
    section_stack: list[dict[str, Any]] = []
    for hn in heading_nodes_sorted:
        level = _infer_heading_level(hn)
        section = {
            "node_id": f"sec:{hn.get('node_id', '')}",
            "type": "section",
            "title": hn.get("text", ""),
            "level": level,
            "page_start": hn.get("page", 1),
            "page_end": hn.get("page", 1),
            "child_ids": [],
            "content_node_ids": [],
            "confidence": float(hn.get("confidence", 1.0) or 1.0),
        }

        # Pop sections that are same level or deeper
        while section_stack and section_stack[-1]["level"] >= level:
            popped = section_stack.pop()
            # Assign end page from last content node
            if popped["content_node_ids"]:
                last_node_id = popped["content_node_ids"][-1]
                for n in nodes:
                    if n.get("node_id") == last_node_id:
                        popped["page_end"] = n.get("page", popped["page_start"])
                        break
            sections.append(popped)

        # Add to parent's children
        if section_stack:
            section_stack[-1]["child_ids"].append(section["node_id"])

        section_stack.append(section)

    # Pop remaining stack
    while section_stack:
        popped = section_stack.pop()
        if popped["content_node_ids"]:
            last_node_id = popped["content_node_ids"][-1]
            for n in nodes:
                if n.get("node_id") == last_node_id:
                    popped["page_end"] = n.get("page", popped["page_start"])
                    break
        sections.append(popped)

    # Assign content nodes to sections
    _assign_content_nodes(nodes, sections)

    return sections


def _infer_heading_level(node: dict[str, Any]) -> int:
    """Infer heading level from node metadata or text style."""
    # Check for explicit level in metadata
    meta = node.get("metadata") or {}
    if "level" in meta:
        return int(meta["level"])

    # Check role
    role = str(node.get("role") or "").lower()
    if role == "title":
        return 1

    # Default: level 1
    return 1


def _assign_content_nodes(
    nodes: list[dict[str, Any]],
    sections: list[dict[str, Any]],
) -> None:
    """Assign content nodes (paragraphs, tables, images, formulas) to their parent sections."""
    if not sections or not nodes:
        return

    sections_sorted = sorted(sections, key=lambda s: s.get("page_start", 1))
    content_nodes = [n for n in nodes if n.get("type") != "heading"]

    for cn in content_nodes:
        cn_page = cn.get("page", 1)

        # Find the last section that starts on or before this node's page
        best_section: dict[str, Any] | None = None
        for sec in sections_sorted:
            if sec.get("page_start", 1) <= cn_page:
                best_section = sec
            else:
                break

        if best_section is not None:
            best_section.setdefault("content_node_ids", []).append(cn.get("node_id", ""))
            # Extend section page_end
            if cn_page > best_section.get("page_end", 1):
                best_section["page_end"] = cn_page


__all__ = [
    "build_outline",
]
