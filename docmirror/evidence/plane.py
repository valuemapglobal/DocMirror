# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""UDTR Evidence Plane.

The Evidence Plane is the first canonical layer in MirrorCore vNext. It turns
input sources into page-scoped physical atoms without deciding final document
semantics.
"""

from __future__ import annotations

import csv
import os
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from email import policy
from email.parser import BytesParser
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from docmirror.layout.normalization import (
    build_identity_trace,
    build_normalization_trace,
    rotation_matrix,
)
from docmirror.layout.normalization.orientation import candidate_from_metadata, orientation_comparison_signals
from docmirror.models.mirror.vnext import EvidenceAtom, EvidenceStore, SourceInfo


@dataclass(frozen=True)
class DocumentSource:
    """Normalized input handle for UDTR intake."""

    value: Any
    kind: str = "unknown"
    source_id: str = "src:0001"
    filename: str = ""
    mime_type: str = ""
    sha256: str = ""
    size_bytes: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_any(cls, value: Any, *, source_id: str = "src:0001") -> DocumentSource:
        if isinstance(value, DocumentSource):
            return value

        from docmirror.models.entities.parse_result import ParseResult

        if isinstance(value, ParseResult):
            provenance = value.provenance
            metadata: dict[str, Any] = {"logical_page_count": value.page_count}
            parser_info = getattr(value, "parser_info", None)
            if parser_info is not None:
                parser_info_data = _model_dump(parser_info)
                if parser_info_data:
                    metadata["parser_info"] = parser_info_data
                structure = parser_info_data.get("structure") if isinstance(parser_info_data, dict) else None
                if isinstance(structure, dict) and structure.get("source_page_count") is not None:
                    metadata["source_page_count"] = int(structure["source_page_count"])
            metadata["page_count"] = int(metadata.get("source_page_count") or value.page_count)
            entities = getattr(value, "entities", None)
            if entities is not None:
                metadata["entities"] = _model_dump(entities)
                metadata["scene"] = str(getattr(entities, "document_type", "") or "")
                domain_specific = getattr(entities, "domain_specific", {}) or {}
                # Preserve original file path from provenance for seal detection
                if provenance is not None:
                    props = getattr(provenance, "document_properties", None) or {}
                    source_path = props.get("source_path") if isinstance(props, dict) else ""
                    if source_path:
                        metadata["source_path"] = str(source_path)
                page_evidence_bundles = _page_evidence_bundles(domain_specific)
                if page_evidence_bundles:
                    metadata["page_evidence_bundles"] = page_evidence_bundles
            logical_tables = getattr(value, "logical_tables", None) or []
            if logical_tables:
                logical_table_refs = []
                for logical_table in logical_tables:
                    item = _model_dump(logical_table)
                    logical_table_refs.append(
                        {
                            "table_id": str(item.get("table_id") or item.get("logical_id") or ""),
                            "logical_id": str(item.get("logical_id") or item.get("table_id") or ""),
                            "source_physical_ids": [str(ref) for ref in item.get("source_physical_ids", [])],
                            "source_pages": [int(page) for page in item.get("source_pages", [])],
                            "page_span": list(item.get("page_span") or []),
                            "merge_method": str(item.get("merge_method") or "none"),
                            "merge_confidence": float(item.get("merge_confidence", 1.0) or 0.0),
                            "quality_passed": bool(item.get("quality_passed", True)),
                            "quality_skip_reason": item.get("quality_skip_reason"),
                        }
                    )
                metadata["logical_table_count"] = len(logical_table_refs)
                metadata["logical_tables"] = logical_table_refs
            sections = getattr(value, "sections", None) or []
            if sections:
                metadata["sections"] = [_model_dump(section) for section in sections]
            annex = getattr(value, "annex", None)
            if annex is not None:
                annex_data = _model_dump(annex)
                pipeline_debug = annex_data.get("pipeline_debug") if isinstance(annex_data, dict) else None
                if pipeline_debug:
                    metadata["pipeline_debug"] = pipeline_debug
            page_projections = _page_projection_dicts(value)
            if page_projections:
                metadata["page_projection_count"] = len(page_projections)
                region_projections = [
                    {
                        "page_number": int(item.get("page_number") or 0),
                        "regions": list(item.get("regions") or []),
                    }
                    for item in page_projections
                    if item.get("regions")
                ]
                if region_projections:
                    metadata["page_projections"] = region_projections
            return cls(
                value=value,
                kind="parse_result",
                source_id=source_id,
                filename=_provenance_filename(provenance),
                mime_type=str(getattr(provenance, "mime_type", "") or ""),
                sha256=str(getattr(provenance, "checksum", "") or ""),
                size_bytes=_int_or_none(getattr(provenance, "file_size", None)),
                metadata=metadata,
            )

        if isinstance(value, str | Path):
            path = Path(value)
            stat_size: int | None = None
            digest = ""
            if path.exists() and path.is_file():
                try:
                    stat_size = path.stat().st_size
                    digest = _sha256_file(path)
                except OSError:
                    stat_size = None
            return cls(
                value=path,
                kind=_kind_from_path(path),
                source_id=source_id,
                filename=path.name,
                mime_type=_mime_from_path(path),
                sha256=digest,
                size_bytes=stat_size,
                metadata={"path": str(path)},
            )

        return cls(value=value, kind=type(value).__name__, source_id=source_id)

    def to_source_info(self, *, page_count: int = 0, metadata: dict[str, Any] | None = None) -> SourceInfo:
        provenance = dict(self.metadata)
        if metadata:
            provenance.update(metadata)
        return SourceInfo(
            source_id=self.source_id,
            filename=self.filename,
            mime_type=self.mime_type,
            sha256=self.sha256,
            size_bytes=self.size_bytes,
            page_count=page_count,
            input_kind=self.kind,
            provenance=provenance,
        )


@dataclass
class EvidencePage:
    page_id: str
    page_index: int
    page_number: int
    width: float | None = None
    height: float | None = None
    original_rotation: int = 0
    normalized_rotation: int = 0
    coordinate_transform: dict[str, Any] = field(default_factory=dict)
    normalization_trace: dict[str, Any] = field(default_factory=dict)
    content_mode: str = "unknown"
    evidence_ids: list[str] = field(default_factory=list)


@dataclass
class EvidencePlane:
    source: SourceInfo
    pages: list[EvidencePage] = field(default_factory=list)
    evidence: EvidenceStore = field(default_factory=EvidenceStore)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        return {
            "pages": len(self.pages),
            "text_atoms": len(self.evidence.text_atoms),
            "visual_atoms": len(self.evidence.visual_atoms),
            "image_atoms": len(self.evidence.image_atoms),
            "vector_atoms": len(self.evidence.vector_atoms),
        }

    def diagnostics_entry(self) -> dict[str, Any]:
        return {
            "stage": "evidence_plane_builder",
            "status": "ok" if not any(d.get("severity") == "error" for d in self.diagnostics) else "warn",
            "counts": self.counts,
            "normalization_decisions": [page.normalization_trace for page in self.pages if page.normalization_trace],
            "diagnostics": self.diagnostics,
        }


class _EvidenceIdFactory:
    def __init__(self) -> None:
        self._counters: dict[tuple[str, str], int] = {}

    def next(self, page_number: int, kind: str) -> str:
        key = (f"{page_number:04d}", kind)
        self._counters[key] = self._counters.get(key, 0) + 1
        return f"ev:{page_number:04d}:{kind}:{self._counters[key]:06d}"


class EvidencePlaneBuilder:
    """Build an EvidencePlane from supported sources."""

    def build(self, source: Any) -> EvidencePlane:
        document_source = DocumentSource.from_any(source)
        if document_source.kind == "parse_result":
            return self._from_parse_result(document_source)
        if document_source.kind == "pdf":
            return self._from_pdf_path(document_source)
        if document_source.kind == "image":
            return self._from_image_path(document_source)
        if document_source.kind == "word":
            return self._from_word_path(document_source)
        if document_source.kind == "spreadsheet":
            return self._from_spreadsheet_path(document_source)
        if document_source.kind == "html":
            return self._from_html_path(document_source)
        if document_source.kind == "email":
            return self._from_email_path(document_source)
        if document_source.kind == "ofd":
            return self._from_ofd_path(document_source)

        plane = EvidencePlane(source=document_source.to_source_info(page_count=0))
        plane.diagnostics.append(
            {
                "severity": "error",
                "message": f"unsupported document source kind: {document_source.kind}",
            }
        )
        return plane

    def _from_parse_result(self, source: DocumentSource) -> EvidencePlane:
        result = source.value
        ids = _EvidenceIdFactory()
        pages: list[EvidencePage] = []
        evidence = EvidenceStore()
        diagnostics: list[dict[str, Any]] = []
        ocr_evidence_by_page = _ocr_text_evidence_by_page(result)

        for page_index, page in enumerate(getattr(result, "pages", []) or []):
            text_atom_start = len(evidence.text_atoms)
            page_number = int(getattr(page, "page_number", page_index + 1) or page_index + 1)
            page_id = _page_id(page_number)
            width = _float_or_none(getattr(page, "width", None))
            height = _float_or_none(getattr(page, "height", None))
            rotation = _normalized_rotation(getattr(page, "rotation", 0))
            page_normalization = _page_normalization_metadata(page)
            provided_transform = dict(getattr(page, "coordinate_transform", None) or {})
            if provided_transform:
                coordinate_transform = provided_transform
                coordinate_transform.setdefault(
                    "source_page_number",
                    int(getattr(page, "source_page_number", None) or page_number),
                )
                normalization_trace = _normalization_trace_from_transform(
                    page_id=page_id,
                    width=width,
                    height=height,
                    rotation=rotation,
                    coordinate_transform=coordinate_transform,
                )
            else:
                normalization_trace = _normalization_trace_from_page(
                    page_id=page_id,
                    width=width,
                    height=height,
                    rotation=rotation,
                    page_normalization=page_normalization,
                )
                coordinate_transform = _coordinate_transform_from_trace(normalization_trace)
            explicit_page_mode = str(getattr(page, "page_mode", None) or "").strip()
            page_record = EvidencePage(
                page_id=page_id,
                page_index=page_index,
                page_number=page_number,
                width=width,
                height=height,
                original_rotation=rotation,
                normalized_rotation=0,
                coordinate_transform=coordinate_transform,
                normalization_trace=normalization_trace,
                content_mode=explicit_page_mode
                or (
                    "scanned_ocr"
                    if page_normalization
                    else ("native_text" if _page_has_parse_content(page) else "unknown")
                ),
            )

            for text in getattr(page, "texts", []) or []:
                atom = _text_atom(
                    ids,
                    page_number=page_number,
                    source_kind="parse_result_text",
                    text=str(getattr(text, "content", "") or ""),
                    bbox=_bbox(getattr(text, "bbox", None)),
                    confidence=_confidence(getattr(text, "confidence", 1.0)),
                    source_refs=list(getattr(text, "evidence_ids", []) or []),
                    metadata={"block_type": "text", "level": str(getattr(getattr(text, "level", ""), "value", ""))},
                )
                if atom:
                    evidence.text_atoms.append(atom)
                    page_record.evidence_ids.append(atom.id)

            for kv in getattr(page, "key_values", []) or []:
                atom = _text_atom(
                    ids,
                    page_number=page_number,
                    source_kind="parse_result_key_value",
                    text=f"{getattr(kv, 'key', '')}: {getattr(kv, 'value', '')}".strip(": "),
                    bbox=_bbox(getattr(kv, "bbox", None)),
                    confidence=_confidence(getattr(kv, "confidence", 1.0)),
                    source_refs=list(getattr(kv, "evidence_ids", []) or []),
                    metadata={"block_type": "key_value", "key": str(getattr(kv, "key", "") or "")},
                )
                if atom:
                    evidence.text_atoms.append(atom)
                    page_record.evidence_ids.append(atom.id)

            for table in getattr(page, "tables", []) or []:
                table_bbox = _bbox(getattr(table, "bbox", None))
                table_metadata = _table_atom_metadata(table)
                table_geometry_owner_assigned = False
                for header_index, header in enumerate(getattr(table, "headers", []) or []):
                    header_metadata = {
                        "block_type": "table",
                        "table_id": str(getattr(table, "table_id", "") or ""),
                        "header_index": header_index,
                    }
                    if not table_geometry_owner_assigned:
                        header_metadata.update(
                            {
                                "table_bbox": table_bbox,
                                "table_geometry_owner": True,
                                **table_metadata,
                            }
                        )
                    atom = _text_atom(
                        ids,
                        page_number=page_number,
                        source_kind="parse_result_table_header",
                        text=str(header),
                        bbox=None,
                        confidence=_confidence(getattr(table, "confidence", 1.0)),
                        source_refs=list(getattr(table, "evidence_ids", []) or []),
                        metadata=header_metadata,
                    )
                    if atom:
                        evidence.text_atoms.append(atom)
                        page_record.evidence_ids.append(atom.id)
                        table_geometry_owner_assigned = True

                for row_index, row in enumerate(getattr(table, "rows", []) or []):
                    for col_index, cell in enumerate(getattr(row, "cells", []) or []):
                        cell_evidence_ids = list(getattr(cell, "evidence_ids", []) or [])
                        cell_token_ids = list(getattr(cell, "token_ids", []) or [])
                        cell_text = str(getattr(cell, "text", "") or "")
                        cell_bbox = _bbox(getattr(cell, "bbox", None))
                        cell_geometry_status = str(getattr(cell, "geometry_status", "missing") or "missing")
                        allow_empty_cell = bool(not cell_text and (cell_evidence_ids or cell_token_ids))
                        cell_metadata = {
                            "block_type": "table",
                            "table_id": str(getattr(table, "table_id", "") or ""),
                            "row_index": row_index,
                            "col_index": col_index,
                            "source_row_index": getattr(cell, "row_index", None),
                            "source_col_index": getattr(cell, "col_index", None),
                            "row_span": max(1, int(getattr(cell, "row_span", 1) or 1)),
                            "col_span": max(1, int(getattr(cell, "col_span", 1) or 1)),
                            "geometry_status": cell_geometry_status,
                            "geometry_source": getattr(cell, "geometry_source", ""),
                            "geometry_confidence": getattr(cell, "geometry_confidence", None),
                            "geometry_loss_reason": getattr(cell, "geometry_loss_reason", None),
                            "token_ids": cell_token_ids,
                            "source_cell_refs": list(getattr(cell, "source_cell_refs", []) or []),
                        }
                        if not table_geometry_owner_assigned:
                            cell_metadata.update(
                                {
                                    "table_bbox": table_bbox,
                                    "table_geometry_owner": True,
                                    **table_metadata,
                                }
                            )
                        atom = _text_atom(
                            ids,
                            page_number=page_number,
                            source_kind="parse_result_table_cell",
                            text=cell_text,
                            bbox=cell_bbox,
                            confidence=_confidence(
                                getattr(cell, "geometry_confidence", None)
                                if getattr(cell, "geometry_confidence", None) is not None
                                else getattr(cell, "confidence", 1.0)
                            ),
                            source_refs=cell_evidence_ids,
                            metadata=cell_metadata,
                            allow_empty=allow_empty_cell,
                        )
                        if atom:
                            evidence.text_atoms.append(atom)
                            page_record.evidence_ids.append(atom.id)
                            table_geometry_owner_assigned = True

            for item_index, item in enumerate(ocr_evidence_by_page.get(page_number, [])):
                atom = _text_atom(
                    ids,
                    page_number=page_number,
                    source_kind=str(item.get("source_kind") or "ocr_evidence"),
                    text=str(item.get("text") or ""),
                    bbox=_bbox(item.get("bbox")),
                    confidence=_confidence(item.get("confidence", 1.0)),
                    source_refs=[str(ref) for ref in item.get("source_refs", []) or []],
                    metadata={
                        "block_type": "text",
                        "granularity": item.get("granularity", "token"),
                        "ocr_evidence_key": item.get("ocr_evidence_key", ""),
                        "ocr_item_index": item_index,
                        **(item.get("metadata") if isinstance(item.get("metadata"), dict) else {}),
                    },
                )
                if atom:
                    evidence.text_atoms.append(atom)
                    page_record.evidence_ids.append(atom.id)

            if ocr_evidence_by_page.get(page_number) and page_record.content_mode == "unknown":
                page_record.content_mode = "scanned_ocr"

            for atom in evidence.text_atoms[text_atom_start:]:
                _attach_page_coordinates(atom, page_record)

            pages.append(page_record)

        # If the source has a filename pointing to an accessible PDF, render pages
        # for seal/signature/visual detection (critical for audit reports and
        # legal documents submitted as ParseResult).
        # Use source.filename (set to full path by MirrorCoreVNext when
        # options.source_filename is provided, e.g. from CLI).
        _pdf_path = source.filename
        if _pdf_path:
            try:
                import fitz

                pdf_path = str(_pdf_path)
                if Path(pdf_path).exists():
                    doc = fitz.open(pdf_path)
                    for page_record in pages:
                        source_pn = int(
                            (page_record.coordinate_transform or {}).get("source_page_number")
                            or page_record.page_number
                        )
                        if source_pn <= 0 or source_pn > len(doc):
                            continue
                        fz_page = doc[source_pn - 1]
                        source_crop = (page_record.coordinate_transform or {}).get("source_crop_bbox")
                        clip = None
                        if isinstance(source_crop, list | tuple) and len(source_crop) == 4:
                            try:
                                clip = fitz.Rect(*(float(value) for value in source_crop))
                            except (TypeError, ValueError):
                                clip = None
                        pix = fz_page.get_pixmap(dpi=100, clip=clip)
                        img_bytes = pix.tobytes("png")
                        # Create an image atom for the rendered page
                        page_id = page_record.page_id
                        img_id = ids.next(page_record.page_number, "image")
                        image_atom = EvidenceAtom(
                            id=img_id,
                            kind="rendered_image",
                            source_kind="pymupdf_page_render",
                            page_id=page_id,
                            bbox=[0.0, 0.0, float(page_record.width or 0.0), float(page_record.height or 0.0)],
                            source_bbox=list(source_crop) if source_crop else None,
                            coordinate_transform=dict(page_record.coordinate_transform or {}),
                            metadata={
                                "dpi": 100,
                                "page_number": page_record.page_number,
                                "source_page_number": source_pn,
                                "source_crop_bbox": list(source_crop) if source_crop else None,
                                "pixel_width": int(pix.width),
                                "pixel_height": int(pix.height),
                                "role": "page_background",
                            },
                        )
                        evidence.image_atoms.append(image_atom)
                        page_record.evidence_ids.append(img_id)
                        # Run seal detection if enabled
                        if _seal_detection_enabled(source.metadata, scene=source.metadata.get("scene", "")):
                            import io

                            import numpy as np
                            from PIL import Image

                            pil_img = Image.open(io.BytesIO(img_bytes))
                            rgb = pil_img.convert("RGB")
                            image_bgr = np.asarray(rgb)[:, :, ::-1]
                            from docmirror.ocr.vision.seal_detector import detect_seals_hybrid

                            detections = detect_seals_hybrid(image_bgr, enable_texture=True)
                            for det in detections[:5]:  # max 5 per page
                                bbox = det.get("bbox", [0, 0, 100, 100])
                                seal_atom = EvidenceAtom(
                                    id=ids.next(page_record.page_number, "visual"),
                                    kind="visual_artifact",
                                    source_kind="seal_detector",
                                    page_id=page_id,
                                    bbox=bbox,
                                    confidence=det.get("confidence", 0.5),
                                    metadata={
                                        "artifact_type": det.get("kind", "seal"),
                                        "detector": "docmirror.ocr.vision.seal_detector.hybrid",
                                        "method": det.get("method", ""),
                                    },
                                )
                                evidence.visual_atoms.append(seal_atom)
                                page_record.evidence_ids.append(seal_atom.id)
                    doc.close()
            except Exception as exc:
                _diag_msg = f"ParseResult seal detection skipped: {exc}"
                import logging as _lg

                _lg.getLogger("docmirror.evidence.plane").debug("[EvPlane] %s", _diag_msg)
                diagnostics.append({"severity": "warning", "message": _diag_msg})

        _finalize_indexes(evidence)
        physical_page_count = int(
            source.metadata.get("source_page_count")
            or source.metadata.get("page_count")
            or len(pages)
            or int(getattr(result, "page_count", 0) or 0)
        )
        plane = EvidencePlane(
            source=source.to_source_info(page_count=physical_page_count),
            pages=pages,
            evidence=evidence,
        )
        plane.diagnostics.extend(diagnostics)
        plane.diagnostics.append({"severity": "info", "message": "built evidence plane from ParseResult"})
        return plane

    def _from_pdf_path(self, source: DocumentSource) -> EvidencePlane:
        backend = str(source.metadata.get("pdf_backend") or os.environ.get("DOCMIRROR_UDTR_PDF_BACKEND") or "")
        if backend.lower() in {"pymupdf", "fitz"}:
            return self._from_pdf_path_pymupdf(source)
        if backend.lower() == "pypdf":
            return self._from_pdf_path_pypdf(source)
        # Auto-detect: prefer PyMuPDF for vector/image + native word boundaries;
        # fall back to pypdf if PyMuPDF is not available.
        try:
            import fitz  # noqa: F401

            return self._from_pdf_path_pymupdf(source)
        except ImportError:
            return self._from_pdf_path_pypdf(source)

    def _from_pdf_path_pypdf(self, source: DocumentSource) -> EvidencePlane:
        path = Path(source.value)
        ids = _EvidenceIdFactory()
        pages: list[EvidencePage] = []
        evidence = EvidenceStore()
        diagnostics: list[dict[str, Any]] = []

        try:
            from pypdf import PdfReader
        except ImportError as exc:
            plane = EvidencePlane(source=source.to_source_info(page_count=0))
            plane.diagnostics.append(
                {
                    "severity": "error",
                    "message": f"pypdf is required for default PDF EvidencePlane intake: {exc}",
                }
            )
            return plane

        try:
            reader = PdfReader(str(path))
        except Exception as exc:
            plane = EvidencePlane(source=source.to_source_info(page_count=0))
            plane.diagnostics.append({"severity": "error", "message": f"failed to open PDF with pypdf: {exc}"})
            return plane

        for page_index, page in enumerate(reader.pages):
            page_number = page_index + 1
            page_id = _page_id(page_number)
            width, height = _pypdf_page_size(page)
            rotation = _pypdf_page_rotation(page)
            normalization_trace = _normalization_trace_from_page(
                page_id=page_id,
                width=width,
                height=height,
                rotation=rotation,
                page_normalization={},
            )
            page_record = EvidencePage(
                page_id=page_id,
                page_index=page_index,
                page_number=page_number,
                width=width,
                height=height,
                original_rotation=rotation,
                normalized_rotation=0,
                coordinate_transform=_coordinate_transform_from_trace(normalization_trace),
                normalization_trace=normalization_trace,
                content_mode="native_text",
            )
            try:
                text = page.extract_text() or ""
            except Exception as exc:
                text = ""
                diagnostics.append(
                    {
                        "severity": "warning",
                        "message": f"pypdf text extraction failed on page {page_number}: {exc}",
                    }
                )

            for line_index, line in enumerate(text.splitlines()):
                for word_index, word in enumerate(line.split()):
                    atom = _text_atom(
                        ids,
                        page_number=page_number,
                        source_kind="pdf_native_pypdf",
                        text=word,
                        bbox=None,
                        confidence=1.0,
                        source_refs=[],
                        metadata={"line_index": line_index, "word_index": word_index},
                    )
                    if atom:
                        evidence.text_atoms.append(atom)
                        page_record.evidence_ids.append(atom.id)

            if not page_record.evidence_ids:
                page_record.content_mode = "unknown"
            pages.append(page_record)

        _finalize_indexes(evidence)
        pdf_outline = _extract_pdf_outline(reader)
        diagnostics.append({"severity": "info", "message": "built evidence plane from PDF native text using pypdf"})
        diagnostics.append({"severity": "info", "message": "pypdf backend does not expose bbox/vector/image atoms"})
        return EvidencePlane(
            source=source.to_source_info(
                page_count=len(pages), metadata={"pdf_outline": pdf_outline} if pdf_outline else {}
            ),
            pages=pages,
            evidence=evidence,
            diagnostics=diagnostics,
        )

    def _from_pdf_path_pymupdf(self, source: DocumentSource) -> EvidencePlane:
        path = Path(source.value)
        ids = _EvidenceIdFactory()
        pages: list[EvidencePage] = []
        evidence = EvidenceStore()
        diagnostics: list[dict[str, Any]] = []
        pdf_provenance = _pypdf_provenance(path, diagnostics)

        try:
            import fitz  # type: ignore[import-not-found]
        except ImportError as exc:
            plane = EvidencePlane(source=source.to_source_info(page_count=0))
            plane.diagnostics.append(
                {
                    "severity": "error",
                    "message": f"PyMuPDF is required for PDF EvidencePlane intake: {exc}",
                }
            )
            return plane

        try:
            doc = fitz.open(path)
        except Exception as exc:
            plane = EvidencePlane(source=source.to_source_info(page_count=0))
            plane.diagnostics.append({"severity": "error", "message": f"failed to open PDF: {exc}"})
            return plane

        try:
            for page_index, page in enumerate(doc):
                page_number = page_index + 1
                page_id = _page_id(page_number)
                rect = page.rect
                rotation = _normalized_rotation(getattr(page, "rotation", 0))
                page_w = float(rect.width)
                page_h = float(rect.height)
                coordinate_transform = _coordinate_transform(page_w, page_h, rotation)
                page_record = EvidencePage(
                    page_id=page_id,
                    page_index=page_index,
                    page_number=page_number,
                    width=page_w,
                    height=page_h,
                    original_rotation=rotation,
                    normalized_rotation=0,
                    coordinate_transform=coordinate_transform,
                    normalization_trace=_normalization_trace_from_transform(
                        page_id=page_id,
                        width=page_w,
                        height=page_h,
                        rotation=rotation,
                        coordinate_transform=coordinate_transform,
                    ),
                    content_mode="native_text",
                )

                for word in page.get_text("words") or []:
                    x0, y0, x1, y1, text, block_no, line_no, word_no = word[:8]
                    source_bbox = [float(x0), float(y0), float(x1), float(y1)]
                    bbox = _normalize_bbox(source_bbox, page_w, page_h, rotation)
                    atom = _text_atom(
                        ids,
                        page_number=page_number,
                        source_kind="pdf_native",
                        text=str(text),
                        bbox=bbox,
                        confidence=1.0,
                        source_refs=[],
                        metadata={
                            "block_no": int(block_no),
                            "line_no": int(line_no),
                            "word_no": int(word_no),
                        },
                        source_bbox=source_bbox,
                        coordinate_transform=coordinate_transform,
                    )
                    if atom:
                        evidence.text_atoms.append(atom)
                        page_record.evidence_ids.append(atom.id)

                for drawing_index, drawing in enumerate(page.get_drawings() or []):
                    source_bbox = _rect_bbox(drawing.get("rect"))
                    if not source_bbox:
                        continue
                    bbox = _normalize_bbox(source_bbox, page_w, page_h, rotation)
                    atom = EvidenceAtom(
                        id=ids.next(page_number, "vector"),
                        kind="rectangle",
                        source_kind="pdf_vector",
                        page_id=page_id,
                        bbox=bbox,
                        source_bbox=source_bbox,
                        coordinate_transform=coordinate_transform,
                        confidence=1.0,
                        metadata={"drawing_index": drawing_index, "drawing_type": drawing.get("type", "")},
                    )
                    evidence.vector_atoms.append(atom)
                    page_record.evidence_ids.append(atom.id)

                try:
                    image_infos = page.get_image_info(xrefs=True) or []
                except Exception:
                    image_infos = []
                for image_index, info in enumerate(image_infos):
                    source_bbox = _bbox(info.get("bbox"))
                    bbox = _normalize_bbox(source_bbox, page_w, page_h, rotation) if source_bbox else None
                    atom = EvidenceAtom(
                        id=ids.next(page_number, "image"),
                        kind="embedded_image",
                        source_kind="pdf_image",
                        page_id=page_id,
                        bbox=bbox,
                        source_bbox=source_bbox,
                        coordinate_transform=coordinate_transform,
                        confidence=1.0,
                        metadata={
                            "image_index": image_index,
                            "xref": info.get("xref"),
                            "width": info.get("width"),
                            "height": info.get("height"),
                        },
                    )
                    evidence.image_atoms.append(atom)
                    page_record.evidence_ids.append(atom.id)

                if not page_record.evidence_ids:
                    page_record.content_mode = "unknown"
                pages.append(page_record)
        finally:
            doc.close()

        _finalize_indexes(evidence)
        diagnostics.append({"severity": "info", "message": "built evidence plane from PDF native objects"})
        return EvidencePlane(
            source=source.to_source_info(page_count=len(pages), metadata=pdf_provenance),
            pages=pages,
            evidence=evidence,
            diagnostics=diagnostics,
        )

    def _from_image_path(self, source: DocumentSource) -> EvidencePlane:
        path = Path(source.value)
        ids = _EvidenceIdFactory()
        pages: list[EvidencePage] = []
        evidence = EvidenceStore()
        frame_infos, diagnostics = _image_frame_infos(path)

        if not frame_infos:
            frame_infos = [{"width": None, "height": None, "frame_index": 0, "format": "", "mode": ""}]

        for page_index, frame_info in enumerate(frame_infos):
            page_number = page_index + 1
            page_id = _page_id(page_number)
            width = _float_or_none(frame_info.get("width"))
            height = _float_or_none(frame_info.get("height"))
            rotation = _normalized_rotation(source.metadata.get("rotation", 0))
            normalization_trace = _normalization_trace_from_page(
                page_id=page_id,
                width=width,
                height=height,
                rotation=rotation,
                page_normalization={},
            )
            ocr_tokens = _metadata_tokens_for_page(source.metadata, page_number=page_number)
            page_record = EvidencePage(
                page_id=page_id,
                page_index=page_index,
                page_number=page_number,
                width=width,
                height=height,
                original_rotation=rotation,
                normalized_rotation=0,
                coordinate_transform=_coordinate_transform_from_trace(normalization_trace),
                normalization_trace=normalization_trace,
                content_mode="scanned_ocr" if ocr_tokens else "image",
            )
            page_bbox = [0.0, 0.0, width, height] if width is not None and height is not None else None
            image_atom = EvidenceAtom(
                id=ids.next(page_number, "image"),
                kind="rendered_image",
                source_kind="image_file",
                page_id=page_id,
                bbox=page_bbox,
                confidence=1.0,
                metadata={
                    "path": str(path),
                    "frame_index": frame_info.get("frame_index", page_index),
                    "format": frame_info.get("format", ""),
                    "mode": frame_info.get("mode", ""),
                    "role": "page_background" if ocr_tokens else "rendered_page",
                },
            )
            evidence.image_atoms.append(image_atom)
            page_record.evidence_ids.append(image_atom.id)

            if _seal_detection_enabled(source.metadata, scene=source.metadata.get("scene", "")):
                seal_atom = _detect_seal_atom(
                    path,
                    ids,
                    page_number=page_number,
                    page_id=page_id,
                    frame_index=int(frame_info.get("frame_index", page_index) or page_index),
                    source_ref=image_atom.id,
                )
                if seal_atom is not None:
                    evidence.visual_atoms.append(seal_atom)
                    page_record.evidence_ids.append(seal_atom.id)

            for token_index, token in enumerate(ocr_tokens):
                text = _token_text(token)
                atom = _text_atom(
                    ids,
                    page_number=page_number,
                    source_kind="metadata_ocr_token",
                    text=text,
                    bbox=_token_bbox(token),
                    confidence=_token_confidence(token),
                    source_refs=_token_source_refs(token),
                    metadata={
                        "block_type": "text",
                        "ocr_token_index": token_index,
                        "ocr_source": _token_source(token),
                    },
                )
                if atom:
                    evidence.text_atoms.append(atom)
                    page_record.evidence_ids.append(atom.id)

            pages.append(page_record)

        _finalize_indexes(evidence)
        diagnostics.append({"severity": "info", "message": "built evidence plane from image file"})
        return EvidencePlane(
            source=source.to_source_info(page_count=len(pages)),
            pages=pages,
            evidence=evidence,
            diagnostics=diagnostics,
        )

    def _from_word_path(self, source: DocumentSource) -> EvidencePlane:
        path = Path(source.value)
        units, diagnostics = _word_text_units(path)
        return _evidence_plane_from_text_units(
            source,
            units,
            input_family="word",
            content_mode="native_text",
            diagnostics=diagnostics,
        )

    def _from_spreadsheet_path(self, source: DocumentSource) -> EvidencePlane:
        path = Path(source.value)
        suffix = path.suffix.lower()
        if suffix in {".csv", ".tsv"}:
            units, diagnostics = _delimited_text_units(path, delimiter="\t" if suffix == ".tsv" else ",")
        else:
            units, diagnostics = _spreadsheet_text_units(path)
        return _evidence_plane_from_text_units(
            source,
            units,
            input_family="spreadsheet",
            content_mode="native_table",
            diagnostics=diagnostics,
        )

    def _from_html_path(self, source: DocumentSource) -> EvidencePlane:
        path = Path(source.value)
        units, diagnostics = _html_text_units(path)
        return _evidence_plane_from_text_units(
            source,
            units,
            input_family="html",
            content_mode="native_text",
            diagnostics=diagnostics,
        )

    def _from_email_path(self, source: DocumentSource) -> EvidencePlane:
        path = Path(source.value)
        units, diagnostics = _email_text_units(path)
        return _evidence_plane_from_text_units(
            source,
            units,
            input_family="email",
            content_mode="native_text",
            diagnostics=diagnostics,
        )

    def _from_ofd_path(self, source: DocumentSource) -> EvidencePlane:
        path = Path(source.value)
        units, diagnostics = _ofd_text_units(path)
        return _evidence_plane_from_text_units(
            source,
            units,
            input_family="ofd",
            content_mode="native_text",
            diagnostics=diagnostics,
        )


def _evidence_plane_from_text_units(
    source: DocumentSource,
    units: list[dict[str, Any]],
    *,
    input_family: str,
    content_mode: str,
    diagnostics: list[dict[str, Any]] | None = None,
) -> EvidencePlane:
    ids = _EvidenceIdFactory()
    evidence = EvidenceStore()
    diagnostics = list(diagnostics or [])
    page_numbers = sorted({_int_or_none(unit.get("page_number")) or 1 for unit in units}) or [1]
    pages: list[EvidencePage] = []
    page_by_number: dict[int, EvidencePage] = {}
    for page_index, page_number in enumerate(page_numbers):
        width = float(_intake_page_width(input_family))
        height = float(_intake_page_height(input_family))
        normalization_trace = _normalization_trace_from_page(
            page_id=_page_id(page_number),
            width=width,
            height=height,
            rotation=0,
            page_normalization={},
        )
        page_record = EvidencePage(
            page_id=_page_id(page_number),
            page_index=page_index,
            page_number=page_number,
            width=width,
            height=height,
            original_rotation=0,
            normalized_rotation=0,
            coordinate_transform=_coordinate_transform_from_trace(normalization_trace),
            normalization_trace=normalization_trace,
            content_mode=content_mode if units else "unknown",
        )
        pages.append(page_record)
        page_by_number[page_number] = page_record

    for unit_index, unit in enumerate(units):
        text = str(unit.get("text") or "").strip()
        if not text:
            continue
        page_number = _int_or_none(unit.get("page_number")) or 1
        page_record = page_by_number.get(page_number)
        if page_record is None:
            continue
        metadata = dict(unit.get("metadata") if isinstance(unit.get("metadata"), dict) else {})
        metadata.setdefault("block_type", "text")
        metadata.setdefault("intake_family", input_family)
        metadata.setdefault("intake_unit_index", unit_index)
        atom = _text_atom(
            ids,
            page_number=page_number,
            source_kind=str(unit.get("source_kind") or f"{input_family}_native_text"),
            text=text,
            bbox=_bbox(unit.get("bbox")) or _synthetic_text_bbox(unit_index),
            confidence=_confidence(unit.get("confidence", 1.0)),
            source_refs=[str(ref) for ref in unit.get("source_refs", []) or []],
            metadata=metadata,
        )
        if atom:
            evidence.text_atoms.append(atom)
            page_record.evidence_ids.append(atom.id)

    if not any(page.evidence_ids for page in pages):
        diagnostics.append({"severity": "warning", "message": f"{input_family} intake produced no text evidence"})
    diagnostics.append({"severity": "info", "message": f"built evidence plane from {input_family} native content"})
    _finalize_indexes(evidence)
    return EvidencePlane(
        source=source.to_source_info(page_count=len(pages), metadata={"intake_family": input_family}),
        pages=pages,
        evidence=evidence,
        diagnostics=diagnostics,
    )


def _word_text_units(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    diagnostics: list[dict[str, Any]] = []
    if path.suffix.lower() != ".docx":
        return [], [
            {"severity": "warning", "message": "raw Word intake requires converter; only .docx native XML is supported"}
        ]
    try:
        with zipfile.ZipFile(path) as zf:
            xml_bytes = zf.read("word/document.xml")
    except Exception as exc:
        return [], [{"severity": "error", "message": f"failed to read DOCX document.xml: {exc}"}]
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        return [], [{"severity": "error", "message": f"failed to parse DOCX XML: {exc}"}]

    units: list[dict[str, Any]] = []
    line_index = 0
    for child in root.iter():
        if _xml_local_name(child.tag) != "body":
            continue
        for node in list(child):
            local = _xml_local_name(node.tag)
            if local == "p":
                text = _xml_text(node)
                if text:
                    units.append(
                        _native_text_unit(
                            text,
                            line_index=line_index,
                            source_kind="word_docx_paragraph",
                            metadata={"block_type": "text", "docx_node": "paragraph"},
                        )
                    )
                    line_index += 1
            elif local == "tbl":
                table_id = f"word_table_{1 + sum(1 for unit in units if (unit.get('metadata') or {}).get('table_id'))}"
                rows = [row for row in node.iter() if _xml_local_name(row.tag) == "tr"]
                table_bbox = _synthetic_table_bbox(line_index, row_count=max(1, len(rows)), col_count=4)
                for row_index, row in enumerate(rows):
                    cells = [cell for cell in list(row) if _xml_local_name(cell.tag) == "tc"]
                    for col_index, cell in enumerate(cells):
                        text = _xml_text(cell)
                        if not text:
                            continue
                        units.append(
                            _native_text_unit(
                                text,
                                line_index=line_index + row_index,
                                col_index=col_index,
                                source_kind="word_docx_table_cell",
                                metadata={
                                    "block_type": "table",
                                    "table_id": table_id,
                                    "table_bbox": table_bbox,
                                    "row_index": row_index,
                                    "col_index": col_index,
                                    "docx_node": "table_cell",
                                },
                            )
                        )
                line_index += max(1, len(rows)) + 1
    return units, diagnostics


def _spreadsheet_text_units(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    diagnostics: list[dict[str, Any]] = []
    if path.suffix.lower() != ".xlsx":
        return [], [
            {
                "severity": "warning",
                "message": "raw spreadsheet intake requires converter; only .xlsx native XML is supported",
            }
        ]
    try:
        with zipfile.ZipFile(path) as zf:
            shared_strings = _xlsx_shared_strings(zf)
            sheet_names = sorted(
                name for name in zf.namelist() if name.startswith("xl/worksheets/") and name.endswith(".xml")
            )
            units: list[dict[str, Any]] = []
            for sheet_index, sheet_name in enumerate(sheet_names, start=1):
                sheet_xml = ET.fromstring(zf.read(sheet_name))
                rows = [row for row in sheet_xml.iter() if _xml_local_name(row.tag) == "row"]
                max_cols = max(
                    (len([cell for cell in list(row) if _xml_local_name(cell.tag) == "c"]) for row in rows), default=1
                )
                table_id = f"xlsx_sheet_{sheet_index}"
                table_bbox = _synthetic_table_bbox(0, row_count=max(1, len(rows)), col_count=max(1, max_cols))
                for row_index, row in enumerate(rows):
                    cells = [cell for cell in list(row) if _xml_local_name(cell.tag) == "c"]
                    for fallback_col_index, cell in enumerate(cells):
                        col_index = _xlsx_cell_col_index(str(cell.attrib.get("r") or "")) or fallback_col_index
                        text = _xlsx_cell_text(cell, shared_strings)
                        if not text:
                            continue
                        units.append(
                            _native_text_unit(
                                text,
                                page_number=sheet_index,
                                line_index=row_index,
                                col_index=col_index,
                                source_kind="xlsx_cell",
                                metadata={
                                    "block_type": "table",
                                    "table_id": table_id,
                                    "table_bbox": table_bbox,
                                    "row_index": row_index,
                                    "col_index": col_index,
                                    "sheet_index": sheet_index,
                                    "sheet_xml": sheet_name,
                                },
                            )
                        )
            return units, diagnostics
    except Exception as exc:
        return [], [{"severity": "error", "message": f"failed to read XLSX native XML: {exc}"}]


def _delimited_text_units(path: Path, *, delimiter: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        rows = list(csv.reader(path.read_text(encoding="utf-8-sig").splitlines(), delimiter=delimiter))
    except Exception as exc:
        return [], [{"severity": "error", "message": f"failed to read delimited spreadsheet: {exc}"}]
    table_bbox = _synthetic_table_bbox(
        0, row_count=max(1, len(rows)), col_count=max((len(row) for row in rows), default=1)
    )
    units: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows):
        for col_index, text in enumerate(row):
            if not str(text).strip():
                continue
            units.append(
                _native_text_unit(
                    str(text),
                    line_index=row_index,
                    col_index=col_index,
                    source_kind="delimited_cell",
                    metadata={
                        "block_type": "table",
                        "table_id": "delimited_sheet_1",
                        "table_bbox": table_bbox,
                        "row_index": row_index,
                        "col_index": col_index,
                    },
                )
            )
    return units, []


def _html_text_units(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        html = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return [], [{"severity": "error", "message": f"failed to read HTML: {exc}"}]
    parser = _VisibleTextHTMLParser()
    parser.feed(html)
    units = [
        _native_text_unit(
            text,
            line_index=index,
            source_kind="html_text",
            metadata={"block_type": "text", "html_text_index": index},
        )
        for index, text in enumerate(parser.texts)
        if text
    ]
    return units, []


def _email_text_units(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
    except Exception as exc:
        return [], [{"severity": "error", "message": f"failed to parse email: {exc}"}]
    lines: list[tuple[str, str]] = []
    for header in ("Subject", "From", "To", "Date"):
        value = message.get(header)
        if value:
            lines.append((f"{header}: {value}", "email_header"))
    for line in _email_body_text(message).splitlines():
        cleaned = line.strip()
        if cleaned:
            lines.append((cleaned, "email_body"))
    units = [
        _native_text_unit(
            text,
            line_index=index,
            source_kind=source_kind,
            metadata={"block_type": "text", "email_part": source_kind},
        )
        for index, (text, source_kind) in enumerate(lines)
    ]
    return units, []


def _ofd_text_units(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        if zipfile.is_zipfile(path):
            texts: list[tuple[str, str]] = []
            with zipfile.ZipFile(path) as zf:
                for name in sorted(zf.namelist()):
                    if not name.lower().endswith(".xml"):
                        continue
                    try:
                        root = ET.fromstring(zf.read(name))
                    except Exception:
                        continue
                    for element in root.iter():
                        local = _xml_local_name(element.tag)
                        if local in {"TextCode", "TextObject", "Title", "DocTitle"}:
                            text = _xml_text(element)
                            if text:
                                texts.append((text, name))
            units = [
                _native_text_unit(
                    text,
                    line_index=index,
                    source_kind="ofd_xml_text",
                    metadata={"block_type": "text", "ofd_xml": xml_name},
                )
                for index, (text, xml_name) in enumerate(texts)
            ]
            return units, []
        text = path.read_text(encoding="utf-8", errors="replace")
        return [
            _native_text_unit(line, line_index=index, source_kind="ofd_text_fallback", metadata={"block_type": "text"})
            for index, line in enumerate(text.splitlines())
            if line.strip()
        ], []
    except Exception as exc:
        return [], [{"severity": "error", "message": f"failed to read OFD: {exc}"}]


def _native_text_unit(
    text: str,
    *,
    line_index: int,
    source_kind: str,
    metadata: dict[str, Any],
    page_number: int = 1,
    col_index: int = 0,
) -> dict[str, Any]:
    return {
        "page_number": page_number,
        "text": text,
        "source_kind": source_kind,
        "bbox": _synthetic_text_bbox(line_index, col_index=col_index),
        "confidence": 0.9,
        "source_refs": [],
        "metadata": metadata,
    }


def _synthetic_text_bbox(line_index: int, *, col_index: int = 0) -> list[float]:
    left = 72.0 + (float(col_index) * 96.0)
    top = 72.0 + (float(line_index) * 18.0)
    return [left, top, min(540.0, left + 88.0), top + 14.0]


def _synthetic_table_bbox(line_index: int, *, row_count: int, col_count: int) -> list[float]:
    top = 72.0 + (float(line_index) * 18.0)
    width = max(120.0, min(468.0, 96.0 * max(1, col_count)))
    height = max(24.0, 18.0 * max(1, row_count))
    return [72.0, top, 72.0 + width, top + height]


def _intake_page_width(input_family: str) -> int:
    return 1024 if input_family == "spreadsheet" else 595


def _intake_page_height(input_family: str) -> int:
    return 768 if input_family == "spreadsheet" else 842


def _xml_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return " ".join(part.strip() for part in element.itertext() if part and part.strip())


def _xml_local_name(tag: Any) -> str:
    return str(tag or "").rsplit("}", 1)[-1]


def _xlsx_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    except Exception:
        return []
    return [_xml_text(item) for item in root.iter() if _xml_local_name(item.tag) == "si"]


def _xlsx_cell_text(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = str(cell.attrib.get("t") or "")
    if cell_type == "inlineStr":
        inline = next((child for child in cell.iter() if _xml_local_name(child.tag) == "is"), None)
        return _xml_text(inline)
    value = next((child.text for child in cell if _xml_local_name(child.tag) == "v"), "")
    value = str(value or "")
    if cell_type == "s":
        index = _int_or_none(value)
        if index is not None and 0 <= index < len(shared_strings):
            return shared_strings[index]
    return value


def _xlsx_cell_col_index(cell_ref: str) -> int | None:
    letters = "".join(ch for ch in cell_ref if ch.isalpha()).upper()
    if not letters:
        return None
    value = 0
    for ch in letters:
        value = value * 26 + (ord(ch) - ord("A") + 1)
    return value - 1


class _VisibleTextHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._ignored_depth = 0
        self.texts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        text = " ".join(str(data or "").split())
        if text:
            self.texts.append(text)


def _email_body_text(message: Any) -> str:
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain":
                try:
                    return str(part.get_content())
                except Exception:
                    continue
        for part in message.walk():
            if part.get_content_type() == "text/html":
                try:
                    parser = _VisibleTextHTMLParser()
                    parser.feed(str(part.get_content()))
                    return "\n".join(parser.texts)
                except Exception:
                    continue
        return ""
    try:
        payload = str(message.get_content())
    except Exception:
        raw_payload = message.get_payload(decode=True) or b""
        payload = raw_payload.decode("utf-8", errors="replace") if isinstance(raw_payload, bytes) else str(raw_payload)
    if message.get_content_type() == "text/html":
        parser = _VisibleTextHTMLParser()
        parser.feed(payload)
        return "\n".join(parser.texts)
    return payload


def _text_atom(
    ids: _EvidenceIdFactory,
    *,
    page_number: int,
    source_kind: str,
    text: str,
    bbox: list[float] | None,
    confidence: float,
    source_refs: list[str],
    metadata: dict[str, Any],
    source_bbox: list[float] | None = None,
    coordinate_transform: dict[str, Any] | None = None,
    allow_empty: bool = False,
) -> EvidenceAtom | None:
    if not text and not allow_empty:
        return None
    return EvidenceAtom(
        id=ids.next(page_number, "text"),
        kind="text_token",
        source_kind=source_kind,
        page_id=_page_id(page_number),
        text=text,
        bbox=bbox,
        source_bbox=source_bbox if source_bbox is not None else bbox,
        coordinate_transform=coordinate_transform or _coordinate_transform(None, None, 0),
        confidence=confidence,
        source_refs=source_refs,
        metadata=metadata,
    )


def _attach_page_coordinates(atom: EvidenceAtom, page: EvidencePage) -> None:
    """Attach the logical-page transform and compute the physical source bbox."""
    transform = dict(page.coordinate_transform or {})
    atom.coordinate_transform = transform
    atom.metadata = {
        **dict(atom.metadata or {}),
        "logical_page_number": page.page_number,
        "source_page_number": int(transform.get("source_page_number") or page.page_number),
    }
    bbox = _bbox(atom.bbox)
    inverse = transform.get("inverse_matrix")
    if bbox and _is_matrix3(inverse):
        atom.source_bbox = _transform_bbox_with_matrix(inverse, bbox)
    elif bbox:
        atom.source_bbox = list(bbox)


def _is_matrix3(value: Any) -> bool:
    return isinstance(value, list) and len(value) == 3 and all(isinstance(row, list) and len(row) == 3 for row in value)


def _transform_bbox_with_matrix(matrix: list[list[float]], bbox: list[float]) -> list[float]:
    x0, y0, x1, y1 = bbox
    points = [
        _apply_coordinate_matrix(matrix, x0, y0),
        _apply_coordinate_matrix(matrix, x1, y0),
        _apply_coordinate_matrix(matrix, x1, y1),
        _apply_coordinate_matrix(matrix, x0, y1),
    ]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return [round(min(xs), 4), round(min(ys), 4), round(max(xs), 4), round(max(ys), 4)]


def _apply_coordinate_matrix(matrix: list[list[float]], x: float, y: float) -> tuple[float, float]:
    return (
        float(matrix[0][0]) * x + float(matrix[0][1]) * y + float(matrix[0][2]),
        float(matrix[1][0]) * x + float(matrix[1][1]) * y + float(matrix[1][2]),
    )


def _finalize_indexes(evidence: EvidenceStore) -> None:
    by_page: dict[str, list[str]] = {}
    by_source: dict[str, list[str]] = {}
    for atom in [*evidence.text_atoms, *evidence.visual_atoms, *evidence.image_atoms, *evidence.vector_atoms]:
        by_page.setdefault(atom.page_id, []).append(atom.id)
        by_source.setdefault(atom.source_kind, []).append(atom.id)
    same_visual_text_candidates = _same_visual_text_candidates(evidence.text_atoms)
    evidence.indexes = {
        "by_page": by_page,
        "by_source": by_source,
        "same_visual_text_candidates": same_visual_text_candidates,
        "dedup_prefer_native_text_ids": sorted(
            {candidate["native_id"] for candidate in same_visual_text_candidates if candidate.get("native_id")}
        ),
        "dedup_suppressed_ocr_text_ids": sorted(
            {candidate["ocr_id"] for candidate in same_visual_text_candidates if candidate.get("ocr_id")}
        ),
    }


def _page_id(page_number: int) -> str:
    return f"page:{page_number:04d}"


def _page_has_parse_content(page: Any) -> bool:
    return bool(getattr(page, "texts", None) or getattr(page, "tables", None) or getattr(page, "key_values", None))


def _table_atom_metadata(table: Any) -> dict[str, Any]:
    """Return compact extraction provenance safe to repeat on table atoms."""
    table_metadata = getattr(table, "metadata", None) or {}
    if not isinstance(table_metadata, dict):
        table_metadata = {}
    geometry = table_metadata.get("geometry") if isinstance(table_metadata.get("geometry"), dict) else {}
    out: dict[str, Any] = {}
    for key in (
        "extraction_layer",
        "extraction_confidence",
        "ocr_rotation",
        "ocr_orientation_score",
        "normalized_page_width",
        "normalized_page_height",
        "text_chars",
        "cjk_ratio",
        "keyword_hits",
        "numeric_tokens",
        "garbage_tokens",
        "early_keywords",
        "comparison_signals",
        "orientation_candidates",
        "preserve_headers",
        "statement_keywords",
        "role",
        "source",
        "page_width",
        "page_height",
    ):
        if key in table_metadata and table_metadata[key] not in (None, "", [], {}):
            out[key] = table_metadata[key]

    if getattr(table, "extraction_layer", "") and "extraction_layer" not in out:
        out["extraction_layer"] = str(getattr(table, "extraction_layer") or "")
    if getattr(table, "extraction_confidence", None) is not None and "extraction_confidence" not in out:
        out["extraction_confidence"] = getattr(table, "extraction_confidence")

    for key in (
        "geometry_source",
        "geometry_confidence",
        "coordinate_system",
        "row_bands",
        "col_bands",
        "merged_cells",
        "cell_bboxes",
        "cell_geometry_status",
        "cell_geometry_loss_reason",
        "cell_evidence_ids",
        "cell_token_ids",
        "cell_confidences",
        "cell_spans",
        "merge_diagnostics",
    ):
        value = geometry.get(key, table_metadata.get(key))
        if value not in (None, "", [], {}):
            out[key] = value
    if out.get("geometry_confidence") is not None:
        out["table_geometry_confidence"] = out["geometry_confidence"]
    return out


def _page_normalization_metadata(page: Any) -> dict[str, Any]:
    candidates = [
        metadata
        for table in getattr(page, "tables", []) or []
        if (metadata := _table_atom_metadata(table))
        and any(
            key in metadata
            for key in (
                "ocr_rotation",
                "ocr_orientation_score",
                "normalized_page_width",
                "normalized_page_height",
            )
        )
    ]
    if not candidates:
        return {}

    def _rank(metadata: dict[str, Any]) -> tuple[float, int]:
        score = _float_or_none(metadata.get("ocr_orientation_score")) or 0.0
        rotation = _int_or_none(metadata.get("ocr_rotation")) or 0
        return score, 1 if rotation % 360 else 0

    selected = max(candidates, key=_rank)
    out: dict[str, Any] = {
        "method": "ocr_orientation_probe",
        "source": "parse_result_table_metadata",
        "coordinate_system": "normalized_display",
    }
    if selected.get("ocr_rotation") is not None:
        out["selected_rotation"] = int(selected["ocr_rotation"]) % 360
    if selected.get("ocr_orientation_score") is not None:
        out["orientation_score"] = float(selected["ocr_orientation_score"])
    if selected.get("normalized_page_width") is not None:
        out["normalized_page_width"] = float(selected["normalized_page_width"])
    if selected.get("normalized_page_height") is not None:
        out["normalized_page_height"] = float(selected["normalized_page_height"])
    out["candidate_count"] = len(candidates)
    out["candidate_rotations"] = sorted(
        {int(metadata.get("ocr_rotation") or metadata.get("selected_rotation") or 0) % 360 for metadata in candidates}
    )
    out["comparison_signals"] = orientation_comparison_signals(selected)
    return out


def _with_page_normalization(
    coordinate_transform: dict[str, Any],
    page_normalization: dict[str, Any],
) -> dict[str, Any]:
    out = dict(coordinate_transform)
    out["page_normalization"] = dict(page_normalization)
    if page_normalization.get("selected_rotation") is not None:
        out["content_rotation_applied"] = int(page_normalization["selected_rotation"]) % 360
    return out


def _normalization_trace_from_page(
    *,
    page_id: str,
    width: float | None,
    height: float | None,
    rotation: int,
    page_normalization: dict[str, Any],
) -> dict[str, Any]:
    if page_normalization:
        selected_rotation = int(page_normalization.get("selected_rotation") or rotation or 0) % 360
        confidence = float(
            page_normalization.get("confidence", page_normalization.get("orientation_score", 1.0)) or 0.0
        )
        trace = build_normalization_trace(
            page_id=page_id,
            source_width=float(width or page_normalization.get("source_width") or 0.0),
            source_height=float(height or page_normalization.get("source_height") or 0.0),
            source_rotation=rotation,
            selected_content_rotation=selected_rotation,
            deskew_angle=float(page_normalization.get("deskew_angle") or 0.0),
            scale=float(page_normalization.get("scale") or 1.0),
            candidates=[candidate_from_metadata(page_normalization)],
            selected_reason=str(page_normalization.get("method") or "ocr_orientation_probe"),
            confidence=min(1.0, max(0.0, confidence / max(confidence, 1.0))),
            metadata=page_normalization,
        )
        return trace.to_dict()

    return build_identity_trace(
        page_id=page_id,
        width=width,
        height=height,
        source_rotation=rotation,
    ).to_dict()


def _normalization_trace_from_transform(
    *,
    page_id: str,
    width: float | None,
    height: float | None,
    rotation: int,
    coordinate_transform: dict[str, Any],
) -> dict[str, Any]:
    trace = _normalization_trace_from_page(
        page_id=page_id,
        width=width,
        height=height,
        rotation=rotation,
        page_normalization={},
    )
    trace["matrix"] = coordinate_transform.get("matrix", trace.get("matrix", []))
    trace["inverse_matrix"] = coordinate_transform.get("inverse_matrix", trace.get("inverse_matrix", []))
    trace["deskew_angle"] = float(coordinate_transform.get("deskew_angle", 0.0) or 0.0)
    trace["scale"] = float(coordinate_transform.get("scale", 1.0) or 1.0)
    return trace


def _coordinate_transform_from_trace(trace: dict[str, Any]) -> dict[str, Any]:
    transform = {
        "source_rotation": int(trace.get("source_rotation") or 0) % 360,
        "normalized_rotation": 0,
        "deskew_angle": float(trace.get("deskew_angle") or 0.0),
        "scale": float(trace.get("scale") or 1.0),
        "source_width": float(trace.get("source_width") or 0.0),
        "source_height": float(trace.get("source_height") or 0.0),
        "matrix": trace.get("matrix")
        or rotation_matrix(
            float(trace.get("source_width") or 0.0),
            float(trace.get("source_height") or 0.0),
            int(trace.get("selected_content_rotation") or 0),
        ),
        "inverse_matrix": trace.get("inverse_matrix") or [],
        "normalization_trace_id": f"norm:{trace.get('page_id', '')}",
    }
    transform["page_normalization"] = {
        "method": trace.get("selected_reason", "identity"),
        "source": "normalization_plane",
        "coordinate_system": "normalized_display",
        "selected_rotation": int(trace.get("selected_content_rotation") or 0) % 360,
        "orientation_score": float(trace.get("candidates", [{}])[0].get("score", trace.get("confidence", 1.0)) or 0.0)
        if trace.get("candidates")
        else float(trace.get("confidence", 1.0) or 0.0),
        "confidence": float(trace.get("confidence", 1.0) or 0.0),
        "normalized_page_width": float(trace.get("display_width") or 0.0),
        "normalized_page_height": float(trace.get("display_height") or 0.0),
        "candidate_count": len(trace.get("candidates") or []),
    }
    first_candidate = (trace.get("candidates") or [{}])[0]
    if isinstance(first_candidate, dict) and isinstance(first_candidate.get("signals"), dict):
        transform["page_normalization"]["comparison_signals"] = dict(first_candidate["signals"])
    if isinstance(first_candidate, dict) and first_candidate.get("rotation") is not None:
        transform["page_normalization"]["candidate_rotations"] = [
            int(candidate.get("rotation") or 0) % 360
            for candidate in trace.get("candidates") or []
            if isinstance(candidate, dict)
        ]
    if transform["page_normalization"]["selected_rotation"]:
        transform["content_rotation_applied"] = transform["page_normalization"]["selected_rotation"]
    return transform


def _bbox(value: Any) -> list[float] | None:
    if not value or not isinstance(value, list | tuple) or len(value) != 4:
        return None
    try:
        return [float(v) for v in value]
    except (TypeError, ValueError):
        return None


def _same_visual_text_candidates(atoms: list[EvidenceAtom]) -> list[dict[str, Any]]:
    native_atoms = [atom for atom in atoms if _is_native_text_atom(atom)]
    ocr_atoms = [atom for atom in atoms if _is_ocr_text_atom(atom)]
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for native in native_atoms:
        native_text = _normalized_visual_text(native.text)
        if not native_text or not native.bbox:
            continue
        for ocr in ocr_atoms:
            if native.page_id != ocr.page_id or not ocr.bbox:
                continue
            if native_text != _normalized_visual_text(ocr.text):
                continue
            overlap = _bbox_iou(native.bbox, ocr.bbox)
            if overlap < 0.7:
                continue
            key = (native.id, ocr.id)
            if key in seen:
                continue
            seen.add(key)
            native.metadata.setdefault("same_visual_text_candidate_ids", []).append(ocr.id)
            ocr.metadata.setdefault("same_visual_text_candidate_ids", []).append(native.id)
            candidates.append(
                {
                    "type": "same_visual_text_candidate",
                    "native_id": native.id,
                    "ocr_id": ocr.id,
                    "page_id": native.page_id,
                    "iou": round(overlap, 4),
                    "dedupe_action": "prefer_native",
                }
            )
    return candidates


def _is_native_text_atom(atom: EvidenceAtom) -> bool:
    return atom.source_kind in {"pdf_native", "pdf_native_pypdf", "parse_result_text"}


def _is_ocr_text_atom(atom: EvidenceAtom) -> bool:
    source = str(atom.source_kind or "").lower()
    return "ocr" in source or source.endswith("_token") or source.endswith("_line")


def _normalized_visual_text(value: Any) -> str:
    return "".join(str(value or "").split()).lower()


def _bbox_iou(left: list[float], right: list[float]) -> float:
    lx0, ly0, lx1, ly1 = left
    rx0, ry0, rx1, ry1 = right
    ix0, iy0 = max(lx0, rx0), max(ly0, ry0)
    ix1, iy1 = min(lx1, rx1), min(ly1, ry1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    intersection = (ix1 - ix0) * (iy1 - iy0)
    left_area = max(0.0, (lx1 - lx0) * (ly1 - ly0))
    right_area = max(0.0, (rx1 - rx0) * (ry1 - ry0))
    union = left_area + right_area - intersection
    return intersection / union if union > 0 else 0.0


def _rect_bbox(rect: Any) -> list[float] | None:
    if rect is None:
        return None
    try:
        return [float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)]
    except AttributeError:
        return _bbox(rect)


def _confidence(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 1.0
    return max(0.0, min(1.0, parsed))


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_pdf_outline(reader) -> list[dict[str, Any]]:
    """Extract PDF outline/bookmarks as structured TOC entries."""
    try:
        outline = reader.outline
        if not outline:
            return []
        result: list[dict[str, Any]] = []
        for item in outline:
            if isinstance(item, list):
                result.extend(_extract_pdf_outline_items(item))
            elif hasattr(item, "title"):
                result.append(
                    {
                        "title": str(getattr(item, "title", "")),
                        "page_number": int(getattr(item, "page_number", 0) or 0),
                    }
                )
        return result
    except Exception:
        return []


def _extract_pdf_outline_items(items: list) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, list):
            result.extend(_extract_pdf_outline_items(item))
        elif hasattr(item, "title"):
            result.append(
                {
                    "title": str(getattr(item, "title", "")),
                    "page_number": int(getattr(item, "page_number", 0) or 0),
                }
            )
    return result


def _pypdf_provenance(path: Path, diagnostics: list[dict[str, Any]]) -> dict[str, Any]:
    """Collect pypdf sidecar metadata without duplicating PyMuPDF text atoms."""
    try:
        from pypdf import PdfReader
    except ImportError:
        diagnostics.append({"severity": "info", "message": "pypdf metadata sidecar unavailable"})
        return {"pdf_intake_backends": ["pymupdf"]}

    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        diagnostics.append({"severity": "warning", "message": f"pypdf metadata sidecar failed: {exc}"})
        return {"pdf_intake_backends": ["pymupdf"]}

    provenance: dict[str, Any] = {"pdf_intake_backends": ["pymupdf", "pypdf"]}
    outline = _extract_pdf_outline(reader)
    if outline:
        provenance["pdf_outline"] = outline
    metadata = _pypdf_metadata(reader)
    if metadata:
        provenance["pdf_metadata"] = metadata
    return provenance


def _pypdf_metadata(reader: Any) -> dict[str, Any]:
    raw = getattr(reader, "metadata", None) or {}
    out: dict[str, Any] = {}
    for key, value in dict(raw).items():
        normalized_key = str(key).lstrip("/")
        if normalized_key:
            out[normalized_key] = str(value)
    return out


def _normalized_rotation(value: Any) -> int:
    try:
        rotation = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return rotation % 360


def _rotate_bbox(bbox: list[float], page_w: float, page_h: float, rotation: int) -> list[float]:
    """Transform bbox from rotated PDF to 0° coordinate system."""
    if rotation not in (90, 180, 270) or not bbox or len(bbox) < 4:
        return list(bbox)
    x0, y0, x1, y1 = bbox[0], bbox[1], bbox[2], bbox[3]
    if rotation == 90:
        return [page_h - y1, x0, page_h - y0, x1]
    if rotation == 180:
        return [page_w - x1, page_h - y1, page_w - x0, page_h - y0]
    if rotation == 270:
        return [y0, page_w - x1, y1, page_w - x0]
    return list(bbox)


def _normalize_bbox(
    bbox: list[float],
    page_w: float,
    page_h: float,
    rotation: int,
) -> list[float]:
    return _rotate_bbox(bbox, page_w, page_h, _normalized_rotation(rotation))


def _coordinate_transform(page_w: float | None, page_h: float | None, rotation: Any) -> dict[str, Any]:
    normalized = _normalized_rotation(rotation)
    source_width = float(page_w or 0.0)
    source_height = float(page_h or 0.0)
    matrix = _rotation_matrix(source_width, source_height, normalized)
    from docmirror.layout.normalization import invert_matrix

    return {
        "source_rotation": normalized,
        "normalized_rotation": 0,
        "deskew_angle": 0.0,
        "scale": 1.0,
        "source_width": source_width,
        "source_height": source_height,
        "matrix": matrix,
        "inverse_matrix": invert_matrix(matrix),
    }


def _rotation_matrix(page_w: float, page_h: float, rotation: int) -> list[list[float]]:
    return rotation_matrix(page_w, page_h, rotation)


def _pypdf_page_rotation(page: Any) -> int:
    try:
        return _normalized_rotation(page.get("/Rotate", 0))
    except Exception:
        return 0


def _page_projection_dicts(result: Any) -> list[dict[str, Any]]:
    out_by_page: dict[int, dict[str, Any]] = {}
    for page in getattr(result, "pages", []) or []:
        page_num = int(getattr(page, "page_number", 0) or 0)
        if page_num <= 0:
            continue
        out_by_page[page_num] = _page_projection_dict_from_parse_page(page, page_num)

    for region in _page_projection_regions_from_domain_specific(result):
        page_num = int(region.get("page_number") or 0)
        if page_num <= 0:
            continue
        item = out_by_page.setdefault(
            page_num,
            {
                "page_number": page_num,
                "coordinate_system": "pdf_points_top_left",
                "flow": {"texts": [], "key_values": []},
                "tables": [],
                "regions": [],
            },
        )
        item.setdefault("regions", []).append({key: value for key, value in region.items() if key != "page_number"})

    for item in out_by_page.values():
        _finalize_page_projection_blocks(item)
    return [out_by_page[page_num] for page_num in sorted(out_by_page)]


def _page_projection_dict_from_parse_page(page: Any, page_num: int) -> dict[str, Any]:
    item: dict[str, Any] = {
        "page_number": page_num,
        "coordinate_system": "pdf_points_top_left",
        "flow": {
            "texts": [_text_block_flow_item(text) for text in getattr(page, "texts", []) or []],
            "key_values": [_key_value_flow_item(kv) for kv in getattr(page, "key_values", []) or []],
        },
        "tables": [_model_dump(table) for table in getattr(page, "tables", []) or []],
        "regions": [],
    }
    width = _float_or_none(getattr(page, "width", None))
    height = _float_or_none(getattr(page, "height", None))
    if width is not None:
        item["width"] = width
    if height is not None:
        item["height"] = height
    return item


def _text_block_flow_item(text: Any) -> dict[str, Any]:
    item = {
        "content": str(getattr(text, "content", "") or ""),
        "bbox": _bbox(getattr(text, "bbox", None)),
        "confidence": _confidence(getattr(text, "confidence", 1.0)),
        "evidence_ids": list(getattr(text, "evidence_ids", []) or []),
    }
    return {key: value for key, value in item.items() if value not in (None, "", [])}


def _key_value_flow_item(kv: Any) -> dict[str, Any]:
    item = {
        "key": str(getattr(kv, "key", "") or ""),
        "value": str(getattr(kv, "value", "") or ""),
        "bbox": _bbox(getattr(kv, "bbox", None)),
        "confidence": _confidence(getattr(kv, "confidence", 1.0)),
        "evidence_ids": list(getattr(kv, "evidence_ids", []) or []),
    }
    return {key: value for key, value in item.items() if value not in (None, "", [])}


def _page_projection_regions_from_domain_specific(result: Any) -> list[dict[str, Any]]:
    domain_specific = getattr(getattr(result, "entities", None), "domain_specific", {}) or {}
    if not isinstance(domain_specific, dict):
        return []
    from docmirror.models.mirror.domain_access import (
        local_structure_evidence_pages_from_domain_specific,
        micro_grid_structures_from_domain_specific,
    )

    regions: list[dict[str, Any]] = []
    micro_index = 0
    for grid in micro_grid_structures_from_domain_specific(domain_specific):
        if not isinstance(grid, dict):
            continue
        page_num = int(grid.get("page") or 0)
        if page_num <= 0:
            continue
        micro_index += 1
        region_id = str(grid.get("grid_id") or f"rg_p{page_num}_micro_grid_{micro_index}")
        regions.append(
            {
                "page_number": page_num,
                "region_id": region_id,
                "kind": "micro_grid",
                "morphology": str(grid.get("morphology") or "S3"),
                "bbox": _bbox(grid.get("bbox")) or [],
                "anchor_text": str(grid.get("anchor_text") or ""),
                "structure": dict(grid),
                "confidence": _confidence(grid.get("confidence", 0.0)),
                **({"schema_hint": str(grid.get("schema_hint"))} if grid.get("schema_hint") else {}),
            }
        )

    local_index = 0
    for evidence in local_structure_evidence_pages_from_domain_specific(domain_specific):
        if not isinstance(evidence, dict):
            continue
        page_num = int(evidence.get("page") or 0)
        if page_num <= 0:
            continue
        for structure in evidence.get("structures") or []:
            if not isinstance(structure, dict):
                continue
            local_index += 1
            kind = _structure_region_kind(structure)
            structure_id = str(structure.get("structure_id") or structure.get("id") or "")
            region_id = structure_id or f"rg_p{page_num}_{kind}_{local_index}"
            regions.append(
                {
                    "page_number": page_num,
                    "region_id": region_id,
                    "kind": kind,
                    "morphology": str(structure.get("morphology") or "S5"),
                    "bbox": _bbox(structure.get("bbox")) or [],
                    "anchor_text": str(structure.get("anchor_text") or structure.get("label") or ""),
                    "structure": dict(structure),
                    "confidence": _confidence(structure.get("confidence", 0.0)),
                    **({"schema_hint": str(structure.get("schema_hint"))} if structure.get("schema_hint") else {}),
                }
            )
    return regions


def _structure_region_kind(structure: dict[str, Any]) -> str:
    raw = str(structure.get("structure_kind") or structure.get("kind") or "").strip()
    if raw in {"field_grid", "label_value_graph"}:
        return raw
    if raw in {"kv", "kv_block", "key_value", "key_value_grid"}:
        return "label_value_graph"
    return "field_grid"


def _finalize_page_projection_blocks(item: dict[str, Any]) -> None:
    regions = [region for region in item.get("regions") or [] if isinstance(region, dict)]
    if not regions:
        return
    blocks: list[dict[str, Any]] = []
    morphology_counts: Counter[str] = Counter()
    reading_order: list[str] = []
    for index, region in enumerate(regions):
        region_id = str(region.get("region_id") or f"region_{index}")
        morphology = str(region.get("morphology") or "")
        if morphology:
            morphology_counts[morphology] += 1
        block_id = f"blk_{region_id}"
        blocks.append(
            {
                "block_id": block_id,
                "morphology": morphology,
                "kind": str(region.get("kind") or ""),
                "ref": f"region:{region_id}",
                "bbox": _bbox(region.get("bbox")) or [],
                "anchor_text": str(region.get("anchor_text") or ""),
                "confidence": _confidence(region.get("confidence", 0.0)),
                **({"schema_hint": str(region.get("schema_hint"))} if region.get("schema_hint") else {}),
            }
        )
        reading_order.append(f"region:{region_id}")
    if blocks:
        item["blocks"] = blocks
        item["reading_order"] = reading_order
        item["reading_order_refs"] = reading_order
    if morphology_counts:
        item["morphology_summary"] = dict(morphology_counts)


def _ocr_text_evidence_by_page(result: Any) -> dict[int, list[dict[str, Any]]]:
    domain_specific = getattr(getattr(result, "entities", None), "domain_specific", {}) or {}
    bundles = _page_evidence_bundles(domain_specific)
    by_page: dict[int, list[dict[str, Any]]] = {}
    seen: set[tuple[int, str, tuple[float, ...] | None, str]] = set()
    for bundle in bundles:
        page_number = _int_or_none(bundle.get("page")) or 0
        if page_number <= 0:
            continue
        for evidence_key in ("micro_grid_evidence", "local_structure_evidence"):
            evidence = bundle.get(evidence_key)
            if not isinstance(evidence, dict):
                continue
            payloads = _ocr_payloads_from_evidence(evidence, page_number=page_number, evidence_key=evidence_key)
            for payload in payloads:
                signature = _ocr_payload_signature(page_number, payload)
                if signature in seen:
                    continue
                seen.add(signature)
                by_page.setdefault(page_number, []).append(payload)
    return by_page


def _page_evidence_bundles(domain_specific: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        from docmirror.models.mirror.page_evidence_bundles import build_page_evidence_bundles
    except Exception:
        bundles = domain_specific.get("_page_evidence_bundles") if isinstance(domain_specific, dict) else []
        return [dict(item) for item in bundles or [] if isinstance(item, dict)]
    return build_page_evidence_bundles(domain_specific)


def _ocr_payloads_from_evidence(
    evidence: dict[str, Any],
    *,
    page_number: int,
    evidence_key: str,
) -> list[dict[str, Any]]:
    tokens = evidence.get("tokens") if isinstance(evidence.get("tokens"), list) else []
    if tokens:
        return [
            {
                "source_kind": f"{evidence_key}_token",
                "text": _token_text(token),
                "bbox": _token_bbox(token),
                "confidence": _token_confidence(token),
                "source_refs": _token_source_refs(token),
                "granularity": "token",
                "ocr_evidence_key": evidence_key,
                "metadata": {
                    "ocr_source": _token_source(token),
                    "source_page": page_number,
                    "source_token_id": _token_id(token),
                },
            }
            for token in tokens
            if _token_text(token) and _token_bbox(token)
        ]
    lines = evidence.get("lines") if isinstance(evidence.get("lines"), list) else []
    return [
        {
            "source_kind": f"{evidence_key}_line",
            "text": _line_text(line),
            "bbox": _line_bbox(line),
            "confidence": _line_confidence(line),
            "source_refs": _line_source_refs(line),
            "granularity": "line",
            "ocr_evidence_key": evidence_key,
            "metadata": {
                "ocr_source": str(evidence.get("source") or "scanned_page_ocr"),
                "source_page": page_number,
                "source_line_id": _line_id(line),
            },
        }
        for line in lines
        if _line_text(line) and _line_bbox(line)
    ]


def _ocr_payload_signature(
    page_number: int,
    payload: dict[str, Any],
) -> tuple[int, str, tuple[float, ...] | None, str]:
    bbox = _bbox(payload.get("bbox"))
    rounded_bbox = tuple(round(float(value), 2) for value in bbox) if bbox else None
    return (
        page_number,
        str(payload.get("text") or ""),
        rounded_bbox,
        str(payload.get("granularity") or ""),
    )


def _token_id(token: Any) -> str:
    if isinstance(token, dict):
        return str(token.get("token_id", token.get("id", "")) or "")
    return str(getattr(token, "token_id", getattr(token, "id", "")) or "")


def _line_text(line: Any) -> str:
    if isinstance(line, dict):
        return str(line.get("text", line.get("content", "")) or "")
    return str(getattr(line, "text", getattr(line, "content", "")) or "")


def _line_bbox(line: Any) -> list[float] | None:
    if isinstance(line, dict):
        return _bbox(line.get("bbox") or line.get("box") or line.get("rect"))
    return _bbox(getattr(line, "bbox", getattr(line, "box", getattr(line, "rect", None))))


def _line_confidence(line: Any) -> float:
    if isinstance(line, dict):
        return _confidence(line.get("confidence", line.get("score", 1.0)))
    return _confidence(getattr(line, "confidence", getattr(line, "score", 1.0)))


def _line_source_refs(line: Any) -> list[str]:
    refs = (
        line.get("source_refs", line.get("evidence_ids", []))
        if isinstance(line, dict)
        else getattr(line, "source_refs", getattr(line, "evidence_ids", []))
    )
    if not isinstance(refs, list | tuple):
        return []
    return [str(ref) for ref in refs]


def _line_id(line: Any) -> str:
    if isinstance(line, dict):
        return str(line.get("line_id", line.get("id", "")) or "")
    return str(getattr(line, "line_id", getattr(line, "id", "")) or "")


def _image_frame_infos(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    diagnostics: list[dict[str, Any]] = []
    try:
        from PIL import Image
    except ImportError as exc:
        diagnostics.append(
            {
                "severity": "warning",
                "message": f"Pillow is required to inspect image dimensions: {exc}",
            }
        )
        return [], diagnostics

    try:
        with Image.open(path) as image:
            frame_count = int(getattr(image, "n_frames", 1) or 1)
            frame_infos: list[dict[str, Any]] = []
            for frame_index in range(frame_count):
                try:
                    image.seek(frame_index)
                except EOFError:
                    break
                frame_infos.append(
                    {
                        "width": float(image.width),
                        "height": float(image.height),
                        "frame_index": frame_index,
                        "format": str(image.format or ""),
                        "mode": str(image.mode or ""),
                    }
                )
            return frame_infos, diagnostics
    except Exception as exc:
        diagnostics.append({"severity": "warning", "message": f"failed to inspect image dimensions: {exc}"})
        return [], diagnostics


def _metadata_tokens_for_page(metadata: dict[str, Any], *, page_number: int) -> list[Any]:
    page_tokens = _tokens_from_page_metadata(metadata, page_number=page_number)
    if page_tokens is not None:
        return page_tokens
    tokens = metadata.get("ocr_tokens", metadata.get("tokens", []))
    if not isinstance(tokens, list):
        return []
    if page_number == 1:
        return [token for token in tokens if _token_page_number(token) in {None, 1}]
    return [token for token in tokens if _token_page_number(token) == page_number]


def _tokens_from_page_metadata(metadata: dict[str, Any], *, page_number: int) -> list[Any] | None:
    pages = metadata.get("pages")
    if not isinstance(pages, list) or page_number < 1 or page_number > len(pages):
        return None
    page_meta = pages[page_number - 1]
    if not isinstance(page_meta, dict):
        return None
    tokens = page_meta.get("ocr_tokens", page_meta.get("tokens", []))
    return tokens if isinstance(tokens, list) else []


def _token_page_number(token: Any) -> int | None:
    if isinstance(token, dict):
        return _int_or_none(token.get("page_number", token.get("page")))
    return _int_or_none(getattr(token, "page_number", getattr(token, "page", None)))


def _token_text(token: Any) -> str:
    if isinstance(token, dict):
        return str(token.get("text", token.get("content", token.get("value", ""))) or "")
    return str(getattr(token, "text", getattr(token, "content", getattr(token, "value", ""))) or "")


def _token_bbox(token: Any) -> list[float] | None:
    if isinstance(token, dict):
        return _bbox(token.get("bbox") or token.get("box") or token.get("rect"))
    return _bbox(getattr(token, "bbox", getattr(token, "box", getattr(token, "rect", None))))


def _token_confidence(token: Any) -> float:
    if isinstance(token, dict):
        return _confidence(token.get("confidence", token.get("score", 1.0)))
    return _confidence(getattr(token, "confidence", getattr(token, "score", 1.0)))


def _token_source_refs(token: Any) -> list[str]:
    refs = (
        token.get("source_refs", token.get("evidence_ids", []))
        if isinstance(token, dict)
        else getattr(token, "source_refs", getattr(token, "evidence_ids", []))
    )
    if not isinstance(refs, list | tuple):
        return []
    return [str(ref) for ref in refs]


def _token_source(token: Any) -> str:
    if isinstance(token, dict):
        return str(token.get("source", token.get("source_kind", "metadata")) or "metadata")
    return str(getattr(token, "source", getattr(token, "source_kind", "metadata")) or "metadata")


def _seal_detection_enabled(metadata: dict[str, Any], scene: str = "") -> bool:
    # Explicit config override wins.
    value = metadata.get("detect_seals")
    if value is not None:
        return str(value).strip().lower() in {"1", "true", "yes", "on"}
    value = os.environ.get("DOCMIRROR_UDTR_DETECT_SEALS", "")
    if value:
        return str(value).strip().lower() in {"1", "true", "yes", "on"}
    # Visual artifact detectors are heuristic and must be explicitly enabled;
    # the page-background image atom already preserves the source visual plane.
    _ = scene
    return False


def _detect_seal_atom(
    path: Path,
    ids: _EvidenceIdFactory,
    *,
    page_number: int,
    page_id: str,
    frame_index: int,
    source_ref: str,
) -> EvidenceAtom | None:
    try:
        import numpy as np
        from PIL import Image

        from docmirror.ocr.vision.seal_detector import detect_seals_hybrid
    except Exception:
        return None
    try:
        with Image.open(path) as image:
            if frame_index:
                image.seek(frame_index)
            rgb = image.convert("RGB")
            image_bgr = np.asarray(rgb)[:, :, ::-1]
        detections = detect_seals_hybrid(image_bgr, enable_texture=True)
    except Exception:
        return None
    if not detections:
        return None
    # Return the highest-confidence detection as the primary seal atom,
    # with additional detections logged as metadata.
    best = max(detections, key=lambda d: d["confidence"])
    bbox = best["bbox"]
    return EvidenceAtom(
        id=ids.next(page_number, "visual"),
        kind="visual_artifact",
        source_kind="seal_detector",
        page_id=page_id,
        bbox=bbox,
        confidence=best["confidence"],
        source_refs=[source_ref],
        metadata={
            "artifact_type": best["kind"],
            "detector": "docmirror.ocr.vision.seal_detector.hybrid",
            "method": best["method"],
            "all_detections": [
                {"kind": d["kind"], "bbox": d["bbox"], "confidence": d["confidence"], "method": d["method"]}
                for d in detections
            ],
        },
    )


def _kind_from_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".tif", ".tiff"}:
        return "image"
    if suffix in {".docx", ".doc"}:
        return "word"
    if suffix in {".xlsx", ".xls", ".csv", ".tsv"}:
        return "spreadsheet"
    if suffix in {".html", ".htm"}:
        return "html"
    if suffix in {".eml", ".msg"}:
        return "email"
    if suffix == ".ofd":
        return "ofd"
    return suffix.lstrip(".") or "unknown"


def _mime_from_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "application/pdf"
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".tif", ".tiff"}:
        return f"image/{'jpeg' if suffix in {'.jpg', '.jpeg'} else suffix.lstrip('.')}"
    if suffix == ".docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if suffix == ".xlsx":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if suffix in {".csv", ".tsv"}:
        return "text/tab-separated-values" if suffix == ".tsv" else "text/csv"
    if suffix in {".html", ".htm"}:
        return "text/html"
    if suffix == ".eml":
        return "message/rfc822"
    if suffix == ".ofd":
        return "application/ofd"
    return ""


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _provenance_filename(provenance: Any) -> str:
    if provenance is None:
        return ""
    props = getattr(provenance, "document_properties", None) or {}
    if isinstance(props, dict):
        source_path = props.get("source_path")
        if source_path:
            return Path(str(source_path)).name
    return ""


def _model_dump(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=True)
    if isinstance(value, dict):
        return dict(value)
    return {}


def _pypdf_page_size(page: Any) -> tuple[float | None, float | None]:
    try:
        box = page.mediabox
        return float(box.width), float(box.height)
    except Exception:
        return None, None


def _add_page_cache(plane, source):
    """Cache pdfplumber pages for downstream CSP access."""
    path = source.value if source else None
    if isinstance(path, (str)):
        try:
            import pdfplumber

            pages = {}
            with pdfplumber.open(str(path)) as pdf:
                for i, pg in enumerate(pdf.pages):
                    pages[str(i)] = pg
            plane.pages_cache = pages
        except Exception:
            pass
    return plane
