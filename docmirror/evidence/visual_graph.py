# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Visual Evidence Graph builder.

GA 1.0 design §5.1–§5.3 / §9 Wave 1: Builds the authoritative
VisualEvidenceGraph from a ParseResult and edition payloads.

Every page, text block, table, cell, field, key-value pair, and quality
issue becomes a VisualNode.  Derivation edges connect fields to their
source cells, blocks, and evidence entries.

Usage::

    from docmirror.evidence.visual_graph import build_visual_evidence_graph
    graph = build_visual_evidence_graph(result, editions=editions)
    print(graph.to_dict())
"""

from __future__ import annotations

from typing import Any

from docmirror.models.visual_evidence import (
    VisualEdge,
    VisualEvidenceGraph,
    VisualNode,
)


def build_visual_evidence_graph(
    result: Any,
    editions: dict[str, Any] | None = None,
    *,
    document_id: str = "",
    task_id: str = "",
    outcome_ledger: Any | None = None,
) -> VisualEvidenceGraph:
    """Build the complete Visual Evidence Graph for a document parse.

    Collects nodes from:
    - Mirror pages (page, text block, table, cell, key-value)
    - Edition payloads (field, record)
    - Quality / outcome data (quality_issue, needs_review, fallback)

    Adds derivation edges from fields to source cells/blocks.
    """
    graph = VisualEvidenceGraph(
        document_id=document_id or _infer_document_id(result),
        task_id=task_id or _infer_task_id(result),
        coordinate_system="pdf_points_top_left",
    )

    pages = list(getattr(result, "pages", []) or [])

    for page_idx, page in enumerate(pages, start=1):
        page_no = int(getattr(page, "page_number", page_idx) or page_idx)
        page_width = float(getattr(page, "width", 595.0) or 595.0)
        page_height = float(getattr(page, "height", 842.0) or 842.0)

        graph.add_page(page_no, width=page_width, height=page_height,
                       image_ref=f"page_images/page_{page_no:03d}.png")

        pid = f"page:p{page_no}"
        graph.add_node(VisualNode(
            id=pid, kind="page", label=f"Page {page_no}",
            page=page_no, bbox=[0, 0, page_width, page_height],
            confidence=float(getattr(page, "confidence", 1.0) or 1.0),
        ))

        # Text block nodes
        for text_idx, text in enumerate(getattr(page, "texts", []) or []):
            content = str(getattr(text, "content", "") or "")
            if not content.strip():
                continue
            nid = f"block:p{page_no}:t{text_idx}"
            conf = float(getattr(text, "confidence", 1.0) or 1.0)
            bbox = getattr(text, "bbox", None)
            src_refs = list(getattr(text, "source_refs", []) or [])

            graph.add_node(VisualNode(
                id=nid, kind="block", label=f"Text #{text_idx}",
                value_preview=content[:200],
                page=page_no, bbox=list(bbox) if bbox else None,
                confidence=conf,
                review=_review_for_confidence(conf),
                source_refs=src_refs,
                metadata={
                    "role": getattr(text, "mirror_role", "") or "",
                    "level": getattr(text, "level", "") or "",
                },
            ))
            graph.add_edge(VisualEdge(
                id=f"edge:page_contains_block:{nid}",
                type="contains", from_node=pid, to_node=nid,
                confidence=1.0,
                provenance={"plane": "Parse Plane", "component": "text_extract"},
            ))

        # Table and cell nodes
        for table_idx, table in enumerate(getattr(page, "tables", []) or []):
            tid = f"table:p{page_no}:t{table_idx}"
            tbbox = getattr(table, "bbox", None)
            tconf = float(getattr(table, "confidence", 1.0) or 1.0)

            graph.add_node(VisualNode(
                id=tid, kind="table", label=f"Table #{table_idx}",
                page=page_no, bbox=list(tbbox) if tbbox else None,
                confidence=tconf, review="auto_accepted",
                metadata={
                    "header_columns": list(getattr(table, "headers", []) or []),
                    "table_id": str(getattr(table, "table_id", "") or ""),
                },
            ))
            graph.add_edge(VisualEdge(
                id=f"edge:page_contains_table:{tid}",
                type="contains", from_node=pid, to_node=tid,
                confidence=1.0,
                provenance={"plane": "Parse Plane", "component": "table_detect"},
            ))

            data_rows = list(getattr(table, "data_rows", []) or getattr(table, "rows", []) or [])
            for row_idx, row in enumerate(data_rows):
                for col_idx, cell in enumerate(getattr(row, "cells", []) or []):
                    value = str(getattr(cell, "cleaned", None) or getattr(cell, "text", "") or "")
                    if not value:
                        continue
                    cid = f"cell:p{page_no}:t{table_idx}:r{row_idx}:c{col_idx}"
                    cconf = float(getattr(cell, "confidence", 1.0) or 0.0)
                    cbbox = getattr(cell, "bbox", None) or getattr(cell, "bbox_norm", None)
                    csrc = list(
                        getattr(cell, "source_cell_refs", [])
                        or getattr(cell, "evidence_ids", [])
                        or []
                    )

                    graph.add_node(VisualNode(
                        id=cid, kind="cell",
                        label=f"Cell r{row_idx}c{col_idx}",
                        value_preview=value[:200],
                        raw_preview=str(getattr(cell, "text", "") or ""),
                        page=page_no, bbox=list(cbbox) if cbbox else None,
                        confidence=cconf, review=_review_for_confidence(cconf),
                        source_refs=csrc,
                        metadata={
                            "row_index": row_idx, "col_index": col_idx,
                            "table_id": str(getattr(table, "table_id", "") or ""),
                        },
                    ))
                    graph.add_edge(VisualEdge(
                        id=f"edge:table_contains_cell:{cid}",
                        type="contains", from_node=tid, to_node=cid,
                        confidence=1.0,
                        provenance={"plane": "Parse Plane", "component": "table_detect"},
                    ))

        # Key-value nodes
        for kv_idx, kv in enumerate(getattr(page, "key_values", []) or []):
            key = str(getattr(kv, "key", "") or "")
            val = str(getattr(kv, "value", "") or "")
            if not key and not val:
                continue
            kvid = f"kv:p{page_no}:kv{kv_idx}"
            kconf = float(getattr(kv, "confidence", 1.0) or 1.0)
            kbbox = getattr(kv, "bbox", None)

            graph.add_node(VisualNode(
                id=kvid, kind="key_value",
                label=key, value_preview=val[:200],
                page=page_no, bbox=list(kbbox) if kbbox else None,
                confidence=kconf, review=_review_for_confidence(kconf),
                source_refs=list(getattr(kv, "source_refs", []) or []),
            ))
            graph.add_edge(VisualEdge(
                id=f"edge:page_contains_kv:{kvid}",
                type="contains", from_node=pid, to_node=kvid,
                confidence=1.0,
                provenance={"plane": "Parse Plane", "component": "kv_extract"},
            ))

    # Edition field nodes (W1-02)
    if editions:
        _build_edition_nodes(graph, editions)

    # Quality / outcome nodes
    if outcome_ledger is not None:
        _build_quality_nodes(graph, outcome_ledger)

    return graph


def _build_edition_nodes(
    graph: VisualEvidenceGraph,
    editions: dict[str, Any],
) -> None:
    for edition, payload in editions.items():
        if not isinstance(payload, dict):
            continue

        meta = payload.get("metadata") or {}
        quality = payload.get("quality") or {}
        conf = float(quality.get("confidence", 0.0) or 0.0)
        source_page = meta.get("source_page")
        support_level = meta.get("support_level", "unknown")
        plugin = payload.get("plugin") or {}
        plugin_name = str(plugin.get("name") or edition)

        eid = f"edition:{edition}"
        graph.add_node(VisualNode(
            id=eid, kind="record", label=f"Edition: {edition}",
            page=int(source_page) if source_page else 0,
            confidence=conf, review="auto_accepted" if conf >= 0.8 else "needs_review",
            edition=edition, support_level=support_level,
            metadata={
                "source_fact_ids": meta.get("source_fact_ids", []),
                "evidence_ids": meta.get("evidence_ids", []),
                "fallback_reason": meta.get("fallback_reason"),
                "plugin": plugin_name,
            },
        ))

        fields = (payload.get("data") or {}).get("fields") or {}
        if isinstance(fields, dict):
            for key, value in fields.items():
                field_path = f"{edition}.data.fields.{key}"
                fid = f"field:{field_path}"
                rendered = "" if value is None else str(value)
                src_ids = meta.get("source_fact_ids", [])
                has_evidence = bool(source_page or meta.get("source_bbox") or src_ids)

                graph.add_node(VisualNode(
                    id=fid, kind="field", label=key,
                    value_preview=rendered[:200],
                    field_path=field_path,
                    page=int(source_page) if source_page else 0,
                    bbox=list(meta.get("source_bbox")) if meta.get("source_bbox") else None,
                    confidence=conf,
                    review="auto_accepted" if (has_evidence and conf >= 0.8)
                    else "needs_review" if has_evidence else "needs_evidence",
                    source_refs=src_ids,
                    edition=edition,
                    support_level=support_level,
                    metadata={
                        "fallback_reason": meta.get("fallback_reason"),
                        "plugin": plugin_name,
                    },
                ))
                graph.add_edge(VisualEdge(
                    id=f"edge:edition_has_field:{fid}",
                    type="contains", from_node=eid, to_node=fid,
                    confidence=conf,
                    provenance={"plane": "Edition Projection Plane",
                                "component": plugin_name},
                ))

                for src_ref in src_ids:
                    _link_field_to_source(graph, fid, src_ref, conf, plugin_name)

        records = (payload.get("data") or {}).get("records") or []
        for rec_idx, record in enumerate(records):
            if not isinstance(record, dict):
                continue
            rid = f"record:{edition}.records[{rec_idx}]"
            rec_src = record.get("source_fact_ids", [])

            graph.add_node(VisualNode(
                id=rid, kind="record",
                label=f"Record #{rec_idx}",
                page=int(source_page) if source_page else 0,
                confidence=float(record.get("confidence", conf) or 0.0),
                review="auto_accepted",
                edition=edition,
                source_refs=rec_src,
            ))
            graph.add_edge(VisualEdge(
                id=f"edge:edition_has_record:{rid}",
                type="contains", from_node=eid, to_node=rid,
                confidence=1.0,
                provenance={"plane": "Edition Projection Plane",
                            "component": plugin_name},
            ))


def _link_field_to_source(
    graph: VisualEvidenceGraph,
    field_id: str,
    src_ref: str,
    confidence: float,
    plugin_name: str,
) -> None:
    for node_id, node in graph.nodes.items():
        if src_ref in node.source_refs or src_ref == node.id:
            graph.add_edge(VisualEdge(
                id=f"edge:field_to_source:{field_id}_to_{node_id}",
                type="derived_from",
                from_node=field_id, to_node=node_id,
                method=plugin_name,
                confidence=confidence,
                provenance={"plane": "Edition Projection Plane",
                            "component": plugin_name},
            ))
            return


def _build_quality_nodes(
    graph: VisualEvidenceGraph,
    outcome_ledger: Any,
) -> None:
    events = getattr(outcome_ledger, "events", []) or []
    for ev in events:
        ev_dict = ev.to_dict() if hasattr(ev, "to_dict") else ev
        status = ev_dict.get("status", "")
        severity = ev_dict.get("severity", "")

        if status in ("failure", "partial", "degraded") or severity in ("error", "fatal"):
            qid = f"quality:{ev_dict.get('event_id', 'unknown')}"
            graph.add_node(VisualNode(
                id=qid, kind="quality_issue",
                label=ev_dict.get("code", ""),
                value_preview=ev_dict.get("message", "")[:200],
                confidence=0.0,
                review="needs_review",
                metadata={
                    "category": ev_dict.get("category", ""),
                    "severity": ev_dict.get("severity", ""),
                    "scope": ev_dict.get("scope", {}),
                },
            ))
            scope = ev_dict.get("scope", {})
            for p in scope.get("pages", []):
                pid = f"page:p{p}"
                if pid in graph.nodes:
                    graph.add_edge(VisualEdge(
                        id=f"edge:quality_affects_page:{qid}_to_{pid}",
                        type="references", from_node=qid, to_node=pid,
                        confidence=1.0,
                    ))


def _review_for_confidence(confidence: float) -> str:
    if confidence <= 0.0:
        return "needs_evidence"
    if confidence < 0.5:
        return "needs_review"
    if confidence < 0.8:
        return "auto_accepted"
    return "auto_accepted"


def _infer_document_id(result: Any) -> str:
    return str(
        getattr(getattr(result, "source", None), "document_id", "")
        or getattr(result, "document_id", "")
        or getattr(result, "file_id", "")
        or ""
    )


def _infer_task_id(result: Any) -> str:
    return str(
        getattr(getattr(result, "source", None), "task_id", "")
        or getattr(result, "task_id", "")
        or ""
    )


__all__ = ["build_visual_evidence_graph"]
