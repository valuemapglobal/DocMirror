# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
ParseResult bridge — maps frozen BaseResult to public ParseResult entities.

Purpose: Assembles pages, blocks, tables, and metadata from the internal
physical extraction representation into the framework ``ParseResult`` model,
including logical-table composition hooks.

Main components: ``ParseResultBridge``, ``_blocks_to_pages``,
``_compose_logical_tables``.

Upstream: ``extraction.extractor`` (physical extraction result), ``table.compose``,
``table.merge``.

Downstream: ``entry.factory``, ``output`` exporters, plugins.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


from docmirror.input.bridge.parse_result_bridge_pages import (
    _blocks_to_pages,
    _infer_cell_value,  # noqa: F401 — re-exported for construction shim
)


class ParseResultBridge:
    """Official converter at the physical-extraction → ParseResult boundary.

    Primary methods:
        - ``from_base_result(base)`` → physical extraction result → ParseResult
        - ``to_base_result(pr)``     → ParseResult → physical extraction result
    """

    # ══════════════════════════════════════════════════════════════════════
    # BaseResult → ParseResult (for adapters that extract to BaseResult)
    # ══════════════════════════════════════════════════════════════════════

    @staticmethod
    def from_base_result(base: BaseResult) -> ParseResult:
        """
        Convert BaseResult → ParseResult.

        Used by adapters (e.g. PDFAdapter) that extract to BaseResult
        and need to convert to ParseResult before the middleware pipeline.

        Mapping:
            - Block(type=table) → TableBlock with CellValue per cell
            - Block(type=text/title) → TextBlock with appropriate level
            - Block(type=key_value) → KeyValuePair
        """
        from docmirror.models.entities.parse_result import (
            ParseResult,
            ParserInfo,
        )

        pages = _blocks_to_pages(base)
        meta = base.metadata or {}
        structure = meta.get("structure")
        if isinstance(structure, dict):
            structure = dict(structure)
            structure.setdefault("raw_full_text_length", len(getattr(base, "full_text", "") or ""))
        pr = ParseResult(
            pages=pages,
            raw_text=getattr(base, "full_text", "") or "",
            parser_info=ParserInfo(
                parser=meta.get("parser", ""),
                elapsed_ms=meta.get("elapsed_ms", 0),
                page_count=len(base.pages),
                structure=structure,
                options={
                    "parse_control": meta.get("parse_control"),
                    "parse_control_fingerprint": meta.get("parse_control_fingerprint"),
                    "selected_pages": meta.get("selected_pages"),
                    "doc_type_hint": meta.get("doc_type_hint"),
                    "doc_type_hint_strength": meta.get("doc_type_hint_strength"),
                },
            ),
            sections=meta.get("sections", []),
        )
        if (
            meta.get("micro_grids")
            or meta.get("page_evidence_bundles")
            or meta.get("scanned_micro_grid_evidence")
            or meta.get("scanned_local_structure_evidence")
        ):
            ds = dict(getattr(pr.entities, "domain_specific", None) or {})
            if meta.get("micro_grids"):
                from docmirror.models.mirror.page_evidence_bundles import merge_micro_grid_structures_into_bundles

                merge_micro_grid_structures_into_bundles(ds, list(meta.get("micro_grids") or []))
            if meta.get("page_evidence_bundles"):
                ds["_page_evidence_bundles"] = list(meta.get("page_evidence_bundles") or [])
            else:
                if meta.get("scanned_micro_grid_evidence") or meta.get("scanned_local_structure_evidence"):
                    from docmirror.models.mirror.page_evidence_bundles import bundles_from_extractor_meta

                    bundles = bundles_from_extractor_meta(
                        scanned_micro_grid_evidence=list(meta.get("scanned_micro_grid_evidence") or []),
                        scanned_local_structure_evidence=list(meta.get("scanned_local_structure_evidence") or []),
                    )
                    if bundles:
                        ds["_page_evidence_bundles"] = bundles
            pr.entities.domain_specific = ds
        # ── Compose logical tables (from extractor metadata or physical pages) ──
        _compose_logical_tables(pr, base_metadata=meta, page_layouts=list(base.pages))
        doc_type_hint = meta.get("doc_type_hint")
        if doc_type_hint:
            ds = dict(getattr(pr.entities, "domain_specific", None) or {})
            ds["user_doc_type_hint"] = str(doc_type_hint)
            ds["user_doc_type_hint_strength"] = str(meta.get("doc_type_hint_strength") or "prefer")
            ds["doc_type_hint_source"] = "user"
            pr.entities.domain_specific = ds

        scene = meta.get("document_scene")
        scene_conf = float(meta.get("scene_confidence") or 0.0)
        if scene and scene not in ("unknown", "generic"):
            ds = dict(getattr(pr.entities, "domain_specific", None) or {})
            ds["extractor_scene_hint"] = scene
            ds["extractor_scene_confidence"] = scene_conf
            pre = meta.get("pre_analysis") or {}
            if isinstance(pre, dict) and pre.get("scene_hint"):
                ds["pre_analyzer_scene_hint"] = pre.get("scene_hint")
            file_name = meta.get("file_name")
            if file_name:
                ds["source_file_name"] = str(file_name)
            pr.entities.domain_specific = ds
        perf = meta.get("perf_breakdown")
        if isinstance(perf, dict) and perf.get("extraction_audit"):
            from docmirror.models.ehl import attach_pipeline_debug

            attach_pipeline_debug(pr, "extraction_audit", perf.get("extraction_audit"))
        try:
            from docmirror.models.ehl import ensure_mirror_annex

            ensure_mirror_annex(pr)
        except Exception:
            pass
        return pr

    @staticmethod
    def to_base_result(pr: ParseResult) -> BaseResult:
        """
        Convert ParseResult → BaseResult for middleware pipeline consumption.

        Mapping:
            - PageContent → PageLayout (1:1)
            - TableBlock.rows → Block(block_type="table", raw_content=List[List[str]])
            - TextBlock → Block(block_type="text"/"title")
            - KeyValuePair → Block(block_type="key_value", raw_content={key: value})
        """
        from docmirror.models.entities.domain import BaseResult, Block, PageLayout

        pages = []
        reading_order = 0

        for page_content in pr.pages:
            blocks = []

            for text in page_content.texts:
                from docmirror.models.entities.parse_result import TextLevel

                block_type = "title" if text.level in (TextLevel.TITLE, TextLevel.H1) else "text"
                blocks.append(
                    Block(
                        block_type=block_type,
                        raw_content=text.content,
                        page=page_content.page_number,
                        reading_order=reading_order,
                        heading_level=(
                            1
                            if text.level == TextLevel.TITLE
                            else 1
                            if text.level == TextLevel.H1
                            else 2
                            if text.level == TextLevel.H2
                            else 3
                            if text.level == TextLevel.H3
                            else None
                        ),
                    )
                )
                reading_order += 1

            for kv in page_content.key_values:
                blocks.append(
                    Block(
                        block_type="key_value",
                        raw_content={kv.key: kv.value},
                        page=page_content.page_number,
                        reading_order=reading_order,
                    )
                )
                reading_order += 1

            for table in page_content.tables:
                # Convert CellValue rows to List[List[str]]
                raw_rows = []
                if table.headers:
                    raw_rows.append(table.headers)
                for row in table.rows:
                    raw_rows.append([c.text for c in row.cells])

                blocks.append(
                    Block(
                        block_type="table",
                        raw_content=raw_rows,
                        page=page_content.page_number,
                        reading_order=reading_order,
                    )
                )
                reading_order += 1

            pages.append(
                PageLayout(
                    page_number=page_content.page_number,
                    blocks=tuple(blocks),
                )
            )

        # Build full text from ParseResult
        full_text = pr.full_text

        # Build metadata from entities + parser_info
        metadata: dict[str, Any] = {
            "source_format": pr.provenance.file_type if pr.provenance else "unknown",
        }
        # Carry entities into metadata for downstream middleware access
        if pr.entities.organization:
            metadata["organization"] = pr.entities.organization
        if pr.entities.subject_name:
            metadata["subject_name"] = pr.entities.subject_name

        return BaseResult(
            pages=tuple(pages),
            full_text=full_text,
            metadata=metadata,
        )


def _deserialize_logical_table_payload(raw: dict) -> LogicalTable:
    """Rebuild a LogicalTable from serialize_logical_tables_for_metadata payload."""
    from docmirror.models.entities.parse_result import (
        CellValue,
        DataType,
        LogicalTable,
        RowProvenance,
        RowType,
        TableRow,
    )

    rows = []
    provenance = []
    table_source_pages = list(raw.get("source_pages") or [])
    table_source_phys = list(raw.get("source_physical_ids") or [])
    fallback_page = int(table_source_pages[0]) if table_source_pages else 1
    fallback_phys = str(table_source_phys[0]) if table_source_phys else f"pt_{fallback_page}_0"
    for ri, raw_row in enumerate(raw.get("rows", [])):
        cells = []
        src_page = int(raw_row.get("source_page") or fallback_page)
        src_phys = str(raw_row.get("source_physical_id") or fallback_phys)
        src_idx = int(raw_row.get("source_row_index") if raw_row.get("source_row_index") is not None else ri)
        if src_idx < 0:
            src_idx = ri
        raw_cells = list(raw_row.get("cells", []) or [])
        row_refs = list(raw_row.get("source_cell_refs") or [])
        if not row_refs:
            row_refs = [
                {"page": src_page, "table_id": src_phys, "row": src_idx, "raw_row": src_idx + 1, "col": ci}
                for ci, _rc in enumerate(raw_cells)
            ]
        for ci, rc in enumerate(raw_cells):
            text = rc.get("text", "")
            dt_str = rc.get("data_type", "text")
            try:
                dt = DataType(dt_str)
            except ValueError:
                dt = DataType.TEXT
            cell_refs = rc.get("source_cell_refs") or ([row_refs[ci]] if ci < len(row_refs) else [])
            cells.append(
                CellValue(
                    text=text,
                    data_type=dt,
                    bbox=rc.get("bbox"),
                    row_index=rc.get("row_index"),
                    col_index=rc.get("col_index"),
                    geometry_status=rc.get("geometry_status", "missing"),
                    geometry_source=rc.get("geometry_source", ""),
                    geometry_confidence=rc.get("geometry_confidence"),
                    geometry_loss_reason=rc.get("geometry_loss_reason"),
                    evidence_ids=list(rc.get("evidence_ids") or []),
                    token_ids=list(rc.get("token_ids") or []),
                    source_cell_refs=list(cell_refs or []),
                )
            )
        rows.append(
            TableRow(
                cells=cells,
                row_type=RowType.DATA,
                source_page=src_page,
                source_physical_id=src_phys,
                source_row_index=src_idx,
                source_cell_refs=row_refs,
            )
        )
        provenance.append(
            RowProvenance(
                source_page=src_page,
                source_table_id=src_phys,
                source_row_index=src_idx,
            )
        )

    sp = raw.get("source_pages", [])
    ps = raw.get("page_span", [1, 1])
    lid = raw.get("logical_id") or raw.get("table_id", "logical_0")
    return LogicalTable(
        table_id=lid,
        logical_id=lid,
        headers=raw.get("headers", []),
        rows=rows,
        row_count=raw.get("row_count", len(rows)),
        source_physical_ids=raw.get("source_physical_ids", []),
        source_pages=sp,
        page_span=(ps[0], ps[1]) if len(ps) >= 2 else (1, 1),
        confidence=raw.get("confidence", 1.0),
        merge_method=raw.get("merge_method", "cross_page_continuation"),
        merge_confidence=raw.get("merge_confidence", raw.get("confidence", 1.0)),
        provenance=provenance,
        merge_log=raw.get("merge_log", []),
        merge_audit=raw.get("merge_audit", []),
        quality_score=float(raw.get("quality_score", 1.0)),
        quality_passed=bool(raw.get("quality_passed", True)),
        quality_skip_reason=raw.get("quality_skip_reason"),
        data_row_estimate=(
            0
            if not raw.get("quality_passed", True)
            else int(raw.get("data_row_estimate") or raw.get("row_count") or len(rows))
        ),
        quality_signals=raw.get("quality_signals") or {},
    )


def _compose_logical_tables(
    pr,
    base_metadata: dict | None = None,
    *,
    page_layouts: list | None = None,
):
    """Compose logical tables from physical pages and set ParseResult.logical_tables.

    Priority:
      1. Pre-composed logical tables from extractor metadata (most accurate —
         composed before destructive merge, preserves cross-page provenance).
      2. Live composition from PageLayout list (same path as extractor Step 4.5).
    """
    from docmirror.tables.compose.composer import build_table_operations

    # Priority 1: Pre-composed from extractor metadata
    raw_tables = None
    if base_metadata:
        raw_tables = base_metadata.get("_logical_tables")

    if raw_tables:
        export_logical = [_deserialize_logical_table_payload(raw) for raw in raw_tables]
        quarantined_raw = (base_metadata or {}).get("quarantined_logical_tables") or []
        quarantined_logical = [_deserialize_logical_table_payload(raw) for raw in quarantined_raw]
        all_logical = export_logical + quarantined_logical
        if all_logical:
            pr.logical_tables = all_logical
            pr.table_operations = build_table_operations(export_logical or all_logical)
            from docmirror.quality.mirror_ltqg import attach_mirror_ltqg

            attach_mirror_ltqg(pr, base_metadata)
            return

    # Priority 2: Live composition — merger quarantine + LTQG export (parity with extractor)
    try:
        from docmirror.tables.compose.export_pipeline import (
            compose_logical_export_from_layouts,
            page_content_to_layouts,
        )

        layouts = list(page_layouts) if page_layouts else page_content_to_layouts(pr.pages)
        if not layouts:
            return

        meta = base_metadata if base_metadata is not None else {}
        pre = meta.get("pre_analysis") if isinstance(meta.get("pre_analysis"), dict) else {}
        export_result = compose_logical_export_from_layouts(
            layouts,
            layout_profile_id=meta.get("layout_profile_id"),
            full_text=pr.full_text or meta.get("full_text") or "",
            scene_hint=pre.get("scene_hint"),
            content_type=pre.get("content_type"),
        )

        if export_result.quarantined_physical:
            meta["quarantined_tables"] = export_result.quarantined_physical
        if export_result.skipped_payload:
            meta["quarantined_logical_tables"] = export_result.skipped_payload
        if export_result.ltqg_summary is not None and export_result.ltqg_summary.enabled:
            meta["ltqg"] = export_result.ltqg_summary.to_dict()
        if export_result.export_payload:
            meta["dual_view"] = True

        if export_result.ltqg_summary is not None and export_result.ltqg_summary.enabled:
            pr.parser_info.structure = dict(pr.parser_info.structure or {})
            from docmirror.evidence.structure_provenance import apply_logical_tables_spe

            pr.parser_info.structure = apply_logical_tables_spe(
                pr.parser_info.structure,
                logical_table_count=len(export_result.export_logical),
                dual_view=bool(export_result.export_payload),
                ltqg_summary=export_result.ltqg_summary.to_dict(),
            )

        plugin_logical = list(export_result.export_logical)
        if export_result.skipped_logical:
            plugin_logical.extend(export_result.skipped_logical)
        if plugin_logical:
            pr.logical_tables = plugin_logical
            pr.table_operations = build_table_operations(export_result.export_logical or plugin_logical)

        from docmirror.quality.mirror_ltqg import attach_mirror_ltqg

        attach_mirror_ltqg(pr, meta)
    except Exception as exc:
        logger.warning("[DocMirror] Bridge logical table composition failed: %s", exc)
