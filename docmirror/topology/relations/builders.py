"""Modular relation builders for UDTR document graphs."""

from __future__ import annotations

from typing import Any

from docmirror.models.mirror.vnext import BlockInfo, GraphEdge


def add_udtr_relation_edges(
    blocks: list[BlockInfo],
    edges: list[GraphEdge],
    *,
    next_edge: Any,
) -> None:
    """Add domain-neutral relation edges that are not part of containment.

    The canonical edge enum remains stable; specialized semantics are stored in
    ``metadata.relation_kind`` so older consumers can still treat these as
    references/metadata edges.
    """

    _add_visual_overlay_reference_edges(blocks, edges, next_edge=next_edge)
    _add_financial_statement_relation_edges(blocks, edges, next_edge=next_edge)
    _add_candidate_derivation_edges(blocks, edges, next_edge=next_edge)


def _add_visual_overlay_reference_edges(
    blocks: list[BlockInfo],
    edges: list[GraphEdge],
    *,
    next_edge: Any,
) -> None:
    overlay_blocks = [block for block in blocks if block.bbox and block.role in {"seal", "signature"}]
    target_blocks = [
        block for block in blocks if block.bbox and block.type not in {"artifact", "header", "footer", "residual"}
    ]
    existing = {
        (edge.from_, edge.to, edge.metadata.get("relation_kind")) for edge in edges if isinstance(edge.metadata, dict)
    }
    for overlay in overlay_blocks:
        for target in target_blocks:
            if overlay.id == target.id or not _shares_page(overlay, target):
                continue
            overlap_ratio = _bbox_overlap_ratio(overlay.bbox, target.bbox)
            if overlap_ratio < 0.1:
                continue
            relation_kind = "signature_of" if overlay.role == "signature" else "seal_overlays"
            key = (overlay.id, target.id, relation_kind)
            if key in existing:
                continue
            edges.append(
                GraphEdge(
                    id=next_edge(),
                    type="references",
                    **{"from": overlay.id},
                    to=target.id,
                    confidence=min(1.0, max(0.1, overlap_ratio)),
                    evidence_ids=list(overlay.evidence_ids),
                    metadata={
                        "source": "udtr_relation_builder",
                        "relation_kind": relation_kind,
                        "overlay_role": overlay.role,
                        "target_type": target.type,
                        "overlap_ratio": round(overlap_ratio, 4),
                    },
                )
            )
            existing.add(key)


def _add_financial_statement_relation_edges(
    blocks: list[BlockInfo],
    edges: list[GraphEdge],
    *,
    next_edge: Any,
) -> None:
    headings = [block for block in blocks if block.type == "heading" and block.text]
    financial_tables = [
        block
        for block in blocks
        if block.type == "table"
        and (block.role == "financial_statement" or (block.content or {}).get("statement_structure"))
    ]
    existing = {
        (edge.from_, edge.to, edge.metadata.get("relation_kind")) for edge in edges if isinstance(edge.metadata, dict)
    }
    for table in financial_tables:
        heading = _nearest_prior_heading(table, headings)
        if heading is not None:
            key = (table.id, heading.id, "statement_part_of")
            if key not in existing:
                edges.append(
                    GraphEdge(
                        id=next_edge(),
                        type="metadata_of",
                        **{"from": table.id},
                        to=heading.id,
                        confidence=0.65,
                        evidence_ids=list(table.evidence_ids[:8]),
                        metadata={
                            "source": "udtr_relation_builder",
                            "relation_kind": "statement_part_of",
                            "statement_type": ((table.content or {}).get("statement_structure") or {}).get(
                                "statement_type", ""
                            ),
                        },
                    )
                )
                existing.add(key)
        _add_statement_note_reference_edges(table, blocks, edges, next_edge=next_edge, existing=existing)


def _add_candidate_derivation_edges(
    blocks: list[BlockInfo],
    edges: list[GraphEdge],
    *,
    next_edge: Any,
) -> None:
    existing = {
        (edge.from_, edge.to, edge.metadata.get("relation_kind")) for edge in edges if isinstance(edge.metadata, dict)
    }
    for block in blocks:
        candidate_ids = _selected_candidate_ids(block)
        for region_id in block.region_ids or []:
            key = (block.id, str(region_id), "derived_from_region_candidate")
            if key in existing:
                continue
            edges.append(
                GraphEdge(
                    id=next_edge(),
                    type="derived_from",
                    **{"from": block.id},
                    to=str(region_id),
                    confidence=block.confidence,
                    evidence_ids=list(block.evidence_ids[:8]),
                    metadata={
                        "source": "udtr_relation_builder",
                        "relation_kind": "derived_from_region_candidate",
                        "candidate_ids": candidate_ids,
                        "region_ids": list(block.region_ids or []),
                    },
                )
            )
            existing.add(key)


def _add_statement_note_reference_edges(
    table: BlockInfo,
    blocks: list[BlockInfo],
    edges: list[GraphEdge],
    *,
    next_edge: Any,
    existing: set[tuple[str, str, Any]],
) -> None:
    structure = (table.content or {}).get("statement_structure") or {}
    rows = [row for row in structure.get("account_rows", []) or [] if isinstance(row, dict) and row.get("note_ref")]
    if not rows:
        return
    note_targets = [block for block in blocks if block.type in {"footnote", "paragraph", "heading"} and block.text]
    for row in rows:
        note_ref = str(row.get("note_ref") or "").strip()
        target = _find_note_target(note_ref, note_targets)
        if target is None:
            continue
        key = (table.id, target.id, "note_refers_to_account")
        if key in existing:
            continue
        edges.append(
            GraphEdge(
                id=next_edge(),
                type="references",
                **{"from": table.id},
                to=target.id,
                confidence=0.6,
                evidence_ids=list(row.get("evidence_ids") or table.evidence_ids[:4]),
                metadata={
                    "source": "udtr_relation_builder",
                    "relation_kind": "note_refers_to_account",
                    "note_ref": note_ref,
                    "account_row_index": row.get("row_index"),
                    "account_label": row.get("label", ""),
                },
            )
        )
        existing.add(key)


def _nearest_prior_heading(table: BlockInfo, headings: list[BlockInfo]) -> BlockInfo | None:
    if not table.page_ids:
        return None
    table_page = str(table.page_ids[0])
    same_page = [heading for heading in headings if table_page in heading.page_ids]
    if same_page:
        return same_page[-1]
    prior = [heading for heading in headings if heading.page_ids and str(heading.page_ids[0]) < table_page]
    return prior[-1] if prior else None


def _find_note_target(note_ref: str, blocks: list[BlockInfo]) -> BlockInfo | None:
    if not note_ref:
        return None
    for block in blocks:
        text = str(block.text or "")
        if note_ref in text:
            return block
    return None


def _selected_candidate_ids(block: BlockInfo) -> list[str]:
    content = block.content or {}
    topology = content.get("topology") if isinstance(content, dict) else None
    if isinstance(topology, dict):
        ids = topology.get("selected_candidate_ids")
        if isinstance(ids, list):
            return [str(value) for value in ids]
    provenance = block.provenance or {}
    if isinstance(provenance, dict):
        ids = provenance.get("selected_candidate_ids")
        if isinstance(ids, list):
            return [str(value) for value in ids]
    return []


def _shares_page(left: BlockInfo, right: BlockInfo) -> bool:
    return bool(set(left.page_ids or []) & set(right.page_ids or []))


def _bbox_overlap_ratio(left: list[float], right: list[float]) -> float:
    lx0, ly0, lx1, ly1 = [float(v) for v in left[:4]]
    rx0, ry0, rx1, ry1 = [float(v) for v in right[:4]]
    ix0, iy0 = max(lx0, rx0), max(ly0, ry0)
    ix1, iy1 = min(lx1, rx1), min(ly1, ry1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    intersection = (ix1 - ix0) * (iy1 - iy0)
    left_area = max((lx1 - lx0) * (ly1 - ly0), 1.0)
    return intersection / left_area
