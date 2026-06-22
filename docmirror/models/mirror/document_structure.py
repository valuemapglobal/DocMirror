# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Document-level logical structure projection — v2 with DFG nodes/edges/reading_flow.

For DFG v2, adds nodes, edges, and reading_flow alongside the existing v1 fields
(outline, flows, suppressed_noise) for backward compatibility.
"""

from __future__ import annotations

from typing import Any

from docmirror.models.mirror.continuity import detect_continuations
from docmirror.models.mirror.document_flow import (
    CrossPageFlow,
    ReadingFlow,
    SectionNode,
    StructureEdge,
    StructureNode,
    StructureRelation,
    SuppressedNoise,
)
from docmirror.models.mirror.noise_policy import detect_repeated_noise
from docmirror.models.mirror.outline import build_outline
from docmirror.models.mirror.relations import resolve_relations


def build_document_structure(
    result: Any,
    document_pages: list[dict[str, Any]] | None = None,
    *,
    profile: str = "structure_v2",
    dfg_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build document-level structure projection with optional DFG v2 output.

    profile values:
      - "legacy": version=1 (current behavior, no DFG)
      - "structure_v2": version=2 with nodes/edges/reading_flow added
      - "ga_full": version=2 with full DFG (nodes/edges/reading_flow/relations)
      - "forensic": version=2 with full DFG plus noise preservation
    """
    outline: list[dict[str, Any]] = []
    flows: list[dict[str, Any]] = []
    suppressed_noise: list[dict[str, Any]] = []
    dfg_nodes: list[dict[str, Any]] = []
    dfg_edges: list[dict[str, Any]] = []
    dfg_reading_flows: list[dict[str, Any]] = []
    dfg_cross_page_flows: list[dict[str, Any]] = []
    dfg_relations: list[dict[str, Any]] = []

    use_dfg = profile in ("structure_v2", "ga_full", "forensic")

    # ── Outline (v1 + v2) ──────────────────────────────────────────────────
    sections = list(getattr(result, "sections", []) or [])
    for idx, section in enumerate(sections, start=1):
        title = str(getattr(section, "title", "") or getattr(section, "name", "") or "").strip()
        if not title:
            continue
        outline.append(
            {
                "node_id": str(getattr(section, "id", "") or f"sec_{idx}"),
                "type": "section",
                "title": title,
                "level": int(getattr(section, "level", 1) or 1),
                "page_start": int(getattr(section, "page_start", 1) or 1),
                "page_end": int(getattr(section, "page_end", None) or getattr(section, "page_start", 1) or 1),
                "children": [],
            }
        )

    if not outline:
        for page in list(document_pages or []) or []:
            page_no = int(page.get("page_number") or 1)
            for text in page.get("texts") or []:
                if not isinstance(text, dict):
                    continue
                level = str(text.get("level") or text.get("text_level") or "").lower()
                content = str(text.get("content") or text.get("text") or "").strip()
                if content and level in {"title", "h1", "h2", "h3"}:
                    outline.append(
                        {
                            "node_id": f"p{page_no}_h{len(outline) + 1}",
                            "type": "section",
                            "title": content,
                            "level": {"title": 1, "h1": 1, "h2": 2, "h3": 3}.get(level, 1),
                            "page_start": page_no,
                            "page_end": page_no,
                            "children": [],
                        }
                    )

    # ── Flows (v1 + v2) ────────────────────────────────────────────────────
    for idx, lt in enumerate(getattr(result, "logical_tables", []) or [], start=1):
        pages = [int(p) for p in (getattr(lt, "source_pages", None) or []) if p is not None]
        if len(set(pages)) > 1:
            flow_entry = {
                "flow_id": f"flow_table_{idx}",
                "type": "cross_page_table",
                "source_pages": sorted(set(pages)),
                "confidence": float(getattr(lt, "merge_confidence", 0.0) or 0.0),
                "evidence_refs": list(getattr(lt, "source_physical_ids", None) or []),
            }
            flows.append(flow_entry)
            if use_dfg:
                dfg_cross_page_flows.append(flow_entry)

    for op in getattr(result, "table_operations", []) or []:
        pages = [int(p) for p in (getattr(op, "source_pages", None) or []) if p is not None]
        if len(set(pages)) > 1:
            flow_entry = {
                "flow_id": f"flow_op_{len(flows) + 1}",
                "type": "cross_page_table",
                "source_pages": sorted(set(pages)),
                "confidence": float(getattr(op, "merge_confidence", 0.0) or 0.0),
                "evidence_refs": list(getattr(op, "source_physical_ids", None) or []),
            }
            flows.append(flow_entry)
            if use_dfg:
                dfg_cross_page_flows.append(flow_entry)

    # ── Noise (v1 + v2) ────────────────────────────────────────────────────
    if document_pages:
        header_pages: list[int] = []
        footer_pages: list[int] = []
        for page in document_pages:
            page_no = int(page.get("page_number") or 0)
            for text in page.get("texts") or []:
                role = str((text or {}).get("mirror_role") or (text or {}).get("level") or "").lower()
                if role == "header":
                    header_pages.append(page_no)
                elif role == "footer":
                    footer_pages.append(page_no)
        if header_pages:
            noise_entry = {"type": "header", "pages": sorted(set(header_pages)), "policy": "excluded_from_markdown"}
            suppressed_noise.append(noise_entry)
        if footer_pages:
            noise_entry = {"type": "footer", "pages": sorted(set(footer_pages)), "policy": "excluded_from_markdown"}
            suppressed_noise.append(noise_entry)

    # ── DFG v2: nodes, edges, reading_flow ─────────────────────────────────
    if use_dfg:
        if dfg_result and dfg_result.get("reading_flow") and dfg_result["reading_flow"].get("global_order"):
            # Use the new DFG engine output
            dfg_nodes, dfg_edges, dfg_reading_flows = _build_dfg_from_engine_result(
                document_pages or [], result, dfg_result
            )
        else:
            dfg_nodes, dfg_edges, dfg_reading_flows = _build_dfg_from_pages(document_pages or [], result)

        # ga_full / forensic: add outline, continuity, noise, relations
        if profile in ("ga_full", "forensic"):
            # Build outline from heading nodes
            dfg_outline = build_outline(dfg_nodes, pages=document_pages)
            for sec in dfg_outline:
                outline.append(sec)

            # Detect paragraph continuations
            continuations = detect_continuations(dfg_nodes)
            for cont in continuations:
                dfg_cross_page_flows.append(cont)

            # Detect repeated noise
            extra_noise = detect_repeated_noise(document_pages or [], profile=profile)
            for noise_item in extra_noise:
                # Avoid duplicates
                existing_types = {(n.get("type"), tuple(sorted(n.get("pages", [])))) for n in suppressed_noise}
                key = (noise_item.get("type"), tuple(sorted(noise_item.get("pages", []))))
                if key not in existing_types:
                    suppressed_noise.append(noise_item)

            # Resolve relations (caption_of, title_of, references)
            dfg_relations = resolve_relations(dfg_nodes, profile=profile)

    output: dict[str, Any] = {
        "version": 2 if use_dfg else 1,
        "outline": outline,
        "flows": flows,
        "suppressed_noise": suppressed_noise,
    }

    if use_dfg:
        output["profile"] = profile
        output["nodes"] = dfg_nodes
        output["edges"] = dfg_edges
        output["reading_flow"] = dfg_reading_flows
        output["cross_page_flows"] = dfg_cross_page_flows
        output["relations"] = dfg_relations
        output["quality"] = {}

    return output


def _build_dfg_from_pages(
    pages: list[dict[str, Any]],
    result: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Build DFG nodes, reading_next edges, and main reading_flow from page content.

    This is the P0 implementation: simple page-level sequential ordering.
    Column-aware ordering (STR-2) and relation resolution (STR-4) are layered on top.
    """
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    reading_flow_node_ids: list[str] = []
    excluded_node_ids: list[str] = []

    global_order = 0
    prev_node_id: str | None = None

    # Collect physical tables for logical table cross-reference
    logical_table_source_ids: set[str] = set()
    for lt in getattr(result, "logical_tables", []) or []:
        for pid in getattr(lt, "source_physical_ids", []) or []:
            logical_table_source_ids.add(str(pid))

    for page in pages:
        page_no = int(page.get("page_number") or 1)

        # Process in reading order: texts, then images, then formulas, then tables
        # For now, we use the order from page dict; column-aware resolver in STR-2
        page_items: list[tuple[int, str, dict[str, Any]]] = []

        for text in page.get("texts") or []:
            if not isinstance(text, dict):
                continue
            ro = int(text.get("reading_order", 0) or 0)
            page_items.append((ro, "text", text))

        for img in page.get("images") or []:
            if not isinstance(img, dict):
                continue
            ro = int(img.get("reading_order", 0) or 0)
            page_items.append((ro, "image", img))

        for fm in page.get("formulas") or []:
            if not isinstance(fm, dict):
                continue
            ro = int(fm.get("reading_order", 0) or 0)
            page_items.append((ro, "formula", fm))

        for tbl in page.get("tables") or []:
            if not isinstance(tbl, dict):
                continue
            ro = int(tbl.get("reading_order", 0) or 0)
            page_items.append((ro, "table", tbl))

        # Also handle key_values as text-like items
        for kv in page.get("key_values") or []:
            if not isinstance(kv, dict):
                continue
            ro = int(kv.get("reading_order", 0) or 0)
            page_items.append((ro, "key_value", kv))

        page_items.sort(key=lambda x: (x[0], x[1]))  # sort by reading_order, then type

        for ro, item_type, item in page_items:
            global_order += 1

            if item_type == "text":
                content = str(item.get("content") or "")
                level = str(item.get("level") or "").lower()
                role = str(item.get("mirror_role") or level or "body")
                node_type = "heading" if level in ("title", "h1", "h2", "h3") else "paragraph"
                node_id = f"node:p{page_no}:t{global_order}"
                nodes.append({
                    "node_id": node_id,
                    "type": node_type,
                    "role": role,
                    "page": page_no,
                    "bbox": item.get("bbox"),
                    "text": content,
                    "fact_refs": [],
                    "evidence_refs": item.get("evidence_ids") or [],
                    "reading_order": global_order,
                    "confidence": float(item.get("confidence", 1.0) or 1.0),
                    "quality_flags": [],
                })
                if role in ("header", "footer", "watermark"):
                    excluded_node_ids.append(node_id)
                else:
                    reading_flow_node_ids.append(node_id)

            elif item_type == "image":
                node_id = f"node:p{page_no}:i{global_order}"
                nodes.append({
                    "node_id": node_id,
                    "type": "image",
                    "role": "body",
                    "page": page_no,
                    "bbox": item.get("bbox"),
                    "text": item.get("caption") or f"[Image: {item.get('image_id', '')}]",
                    "fact_refs": [],
                    "evidence_refs": [],
                    "reading_order": global_order,
                    "confidence": 1.0,
                    "quality_flags": [],
                })
                reading_flow_node_ids.append(node_id)

            elif item_type == "formula":
                node_id = f"node:p{page_no}:f{global_order}"
                latex = str(item.get("latex") or "")
                raw = str(item.get("raw") or "")
                nodes.append({
                    "node_id": node_id,
                    "type": "formula",
                    "role": "body",
                    "page": page_no,
                    "bbox": item.get("bbox"),
                    "text": latex or raw,
                    "fact_refs": [],
                    "evidence_refs": item.get("evidence_ids") or [],
                    "reading_order": global_order,
                    "confidence": float(item.get("confidence", 1.0) or 1.0),
                    "quality_flags": [],
                })
                reading_flow_node_ids.append(node_id)

            elif item_type == "table":
                table_id = str(item.get("table_id") or "")
                is_logical = table_id in logical_table_source_ids
                node_id = f"node:p{page_no}:tb{global_order}"
                nodes.append({
                    "node_id": node_id,
                    "type": "logical_table" if is_logical else "physical_table",
                    "role": "body",
                    "page": page_no,
                    "bbox": item.get("bbox"),
                    "text": "",
                    "fact_refs": [table_id] if table_id else [],
                    "evidence_refs": item.get("evidence_ids") or [],
                    "reading_order": global_order,
                    "confidence": float(item.get("confidence", 1.0) or 1.0),
                    "quality_flags": [],
                })
                reading_flow_node_ids.append(node_id)

            elif item_type == "key_value":
                node_id = f"node:p{page_no}:kv{global_order}"
                nodes.append({
                    "node_id": node_id,
                    "type": "paragraph",
                    "role": "body",
                    "page": page_no,
                    "bbox": item.get("bbox"),
                    "text": f"{item.get('key', '')}: {item.get('value', '')}",
                    "fact_refs": [],
                    "evidence_refs": item.get("evidence_ids") or [],
                    "reading_order": global_order,
                    "confidence": float(item.get("confidence", 1.0) or 1.0),
                    "quality_flags": [],
                })
                reading_flow_node_ids.append(node_id)

            # Build reading_next edge
            if prev_node_id is not None:
                edges.append({
                    "edge_id": f"edge:{prev_node_id}:{node_id}",
                    "type": "reading_next",
                    "from_node": prev_node_id,
                    "to_node": node_id,
                    "confidence": 0.98,
                    "policy": "page_sequential_reading_order_v1",
                    "evidence_refs": [f"layout:p{page_no}"],
                })
            prev_node_id = node_id

    # Build reading_flow
    reading_flows: list[dict[str, Any]] = []
    if reading_flow_node_ids:
        pages_set = set()
        for n in nodes:
            if n["node_id"] in reading_flow_node_ids:
                pages_set.add(n.get("page", 1))
        reading_flows.append({
            "flow_id": "reading_flow:main",
            "type": "main_reading_order",
            "node_ids": reading_flow_node_ids,
            "source_pages": sorted(pages_set),
            "confidence": 0.94,
            "profile": "human_default",
            "excluded_node_ids": excluded_node_ids,
            "policy": "page_sequential_reading_order_v1",
        })

    return nodes, edges, reading_flows


def _build_dfg_from_engine_result(
    pages: list[dict[str, Any]],
    result: Any,
    dfg_result: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Build DFG nodes, edges, and reading_flow from the DFG engine output.

    This replaces _build_dfg_from_pages when the new core/structure/ engine
    produces a valid result. Uses column-aware reading order from the engine.
    """
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    reading_flow_node_ids: list[str] = []
    excluded_node_ids: list[str] = []

    # Build block lookup: (page_number, block_index) -> block dict
    block_lookup: dict[tuple[int, int], dict[str, Any]] = {}
    for page in pages:
        page_no = int(page.get("page_number") or 0)
        blocks = page.get("blocks") or page.get("texts") or []
        for idx, block in enumerate(blocks):
            if isinstance(block, dict):
                block_lookup[(page_no, idx)] = block

    # Use the engine's global reading order
    reading_flow_data = dfg_result.get("reading_flow") or {}
    global_order_list = reading_flow_data.get("global_order") or []

    prev_node_id: str | None = None
    global_order = 0

    for ordered_block in global_order_list:
        if not isinstance(ordered_block, dict):
            continue

        global_order += 1
        page_no = int(ordered_block.get("page_number") or 0)
        block_idx = int(ordered_block.get("block_index") or 0)

        block = block_lookup.get((page_no, block_idx))
        node_id = ordered_block.get("node_id") or f"node:p{page_no}:b{block_idx}"

        if block:
            text = str(block.get("text") or block.get("content") or "").strip()
            bbox = block.get("bbox")
        else:
            text = ""
            bbox = ordered_block.get("bbox")

        # Determine node type from block properties
        node_type = "paragraph"
        role = "body"

        if block:
            level = str(block.get("level") or block.get("text_level") or "").lower()
            mirror_role = str(block.get("mirror_role") or "").lower()
            if level in ("title", "h1", "h2", "h3"):
                node_type = "heading"
            if mirror_role in ("header", "footer", "watermark"):
                role = mirror_role

        nodes.append({
            "node_id": node_id,
            "type": node_type,
            "role": role,
            "page": page_no,
            "bbox": bbox,
            "text": text,
            "fact_refs": [],
            "evidence_refs": [],
            "reading_order": global_order,
            "confidence": 0.98,
            "quality_flags": [],
        })

        if role in ("header", "footer", "watermark"):
            excluded_node_ids.append(node_id)
        else:
            reading_flow_node_ids.append(node_id)

        # Build reading_next edge
        if prev_node_id:
            edges.append({
                "edge_id": f"edge:{prev_node_id}:{node_id}",
                "type": "reading_next",
                "from_node": prev_node_id,
                "to_node": node_id,
                "confidence": 0.98,
                "policy": "column_aware_reading_order_v2",
                "evidence_refs": [],
            })
        prev_node_id = node_id

    # Also process images, tables, key_values not in the engine output
    # The engine only handles blocks with bbox; tables/images are handled separately
    for page in pages:
        page_no = int(page.get("page_number") or 1)

        for img in page.get("images") or []:
            if not isinstance(img, dict):
                continue
            global_order += 1
            node_id = f"node:p{page_no}:i{global_order}"
            nodes.append({
                "node_id": node_id,
                "type": "image",
                "role": "body",
                "page": page_no,
                "bbox": img.get("bbox"),
                "text": str(img.get("caption") or f"[Image: {img.get('image_id', '')}]"),
                "fact_refs": [],
                "evidence_refs": img.get("evidence_ids") or [],
                "reading_order": global_order,
                "confidence": float(img.get("confidence", 1.0) or 1.0),
                "quality_flags": [],
            })
            reading_flow_node_ids.append(node_id)

        for tbl in page.get("tables") or []:
            if not isinstance(tbl, dict):
                continue
            global_order += 1
            node_id = f"node:p{page_no}:tb{global_order}"
            nodes.append({
                "node_id": node_id,
                "type": "physical_table",
                "role": "body",
                "page": page_no,
                "bbox": tbl.get("bbox"),
                "text": "",
                "fact_refs": [str(tbl.get("table_id") or "")],
                "evidence_refs": tbl.get("evidence_ids") or [],
                "reading_order": global_order,
                "confidence": float(tbl.get("confidence", 1.0) or 1.0),
                "quality_flags": [],
            })
            reading_flow_node_ids.append(node_id)

    # Build reading_flow
    reading_flows: list[dict[str, Any]] = []
    if reading_flow_node_ids:
        pages_set = set()
        for n in nodes:
            if n["node_id"] in reading_flow_node_ids:
                pages_set.add(n.get("page", 1))
        reading_flows.append({
            "flow_id": "reading_flow:main",
            "type": "main_reading_order",
            "node_ids": reading_flow_node_ids,
            "source_pages": sorted(pages_set),
            "confidence": 0.95,
            "profile": "human_default",
            "excluded_node_ids": excluded_node_ids,
            "policy": "column_aware_reading_order_v2",
        })

    # Add section tree from DFG engine to edges
    section_tree = dfg_result.get("section_tree") or {}
    flat_headings = section_tree.get("flat_headings") or []
    prev_heading: dict[str, Any] | None = None
    for heading in flat_headings:
        if not isinstance(heading, dict):
            continue
        heading_node_id = heading.get("node_id") or ""
        if heading_node_id:
            edges.append({
                "edge_id": f"edge:section:{heading_node_id}",
                "type": "section_child",
                "from_node": prev_heading.get("node_id", "") if prev_heading else "root",
                "to_node": heading_node_id,
                "confidence": float(heading.get("confidence", 0.9) or 0.9),
                "policy": "multi_language_section_detection_v1",
                "evidence_refs": [],
            })
            prev_heading = heading

    # Add cross-page bridges as edges
    bridges = dfg_result.get("cross_page_bridges") or {}
    bridge_list = bridges.get("bridges") or []
    for bridge in bridge_list:
        if not isinstance(bridge, dict):
            continue
        bridge_id = bridge.get("bridge_id") or ""
        page_a = int(bridge.get("page_a") or 0)
        block_a_idx = int(bridge.get("block_a_index") or 0)
        page_b = int(bridge.get("page_b") or 0)
        block_b_idx = int(bridge.get("block_b_index") or 0)
        confidence = float(bridge.get("confidence", 0.5) or 0.5)

        from_node = f"node:p{page_a}:b{block_a_idx}"
        to_node = f"node:p{page_b}:b{block_b_idx}"

        edges.append({
            "edge_id": f"edge:{bridge_id}",
            "type": "continues",
            "from_node": from_node,
            "to_node": to_node,
            "confidence": confidence,
            "policy": "cross_page_continuity_v1",
            "evidence_refs": [],
        })

    return nodes, edges, reading_flows
