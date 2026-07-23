# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
VAT invoice community domain plugin.

Premium community plugin for Chinese VAT invoices (key-value archetype). Declares
identity field label specs, builds minimal DEC via ``build_domain_data``, and
implements ``recognize`` with ``extract_kv_community_output`` plus VAT-specific
OCR field normalization.

Pipeline role: one of six premium plugins; ``runner`` invokes ``recognize``
when it returns records/fields, otherwise falls back to ``build_domain_data``.

Key exports: ``VATInvoicePlugin``, ``plugin``.

Dependencies: ``DomainPlugin``, ``dec_builder``, ``kv_community_extract``,
``kv_community_enrich.enrich_vat_invoice_output``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from docmirror.plugin_api import DomainPlugin, FactPatch


class VATInvoicePlugin(DomainPlugin):
    """Community edition plugin for VAT invoice document processing."""

    @property
    def domain_name(self) -> str:
        return "vat_invoice"

    @property
    def display_name(self) -> str:
        return "VAT Invoice (Community)"

    @property
    def edition(self) -> str:
        return "community"

    @property
    def identity_fields(self) -> Sequence[tuple[str, Sequence[str]]]:
        return (
            ("invoice_number", ("发票号码", "Invoice No", "发票号")),
            ("invoice_code", ("发票代码", "Invoice Code")),
            ("seller_name", ("销售方名称", "卖方名称", "Seller")),
            ("buyer_name", ("购买方名称", "买方名称", "Buyer")),
            ("total_amount", ("价税合计", "Total", "金额")),
            ("invoice_date", ("开票日期", "Date", "日期")),
        )

    def build_domain_data(self, _metadata, entities):
        from docmirror.plugins._base.dec_builder import build_dec_kv

        return build_dec_kv(
            "vat_invoice",
            {
                "invoice_number": entities.get("invoice_number", ""),
                "invoice_code": entities.get("invoice_code", ""),
                "seller_name": entities.get("seller_name", ""),
                "buyer_name": entities.get("buyer_name", ""),
                "total_amount": entities.get("total_amount", ""),
            },
        )

    def recognize(self, parse_result, text: str = ""):
        from pathlib import Path

        from docmirror.models.edition_serializer import EditionContext, edition_serializer
        from docmirror.models.entities.domain_result import DomainExtractionResult, DomainQuality
        from docmirror.plugins._base.kv_community_enrich import enrich_vat_invoice_output
        from docmirror.plugins._base.kv_community_extract import extract_kv_community_output
        from docmirror.plugins.vat_invoice.semantic_solver import VATInvoiceSemanticSolver

        solution = VATInvoiceSemanticSolver().solve(full_text=text, parse_result=parse_result)
        fields, canonical_warnings = _canonicalize_vat_fields(
            dict((solution.canonical_model or {}).get("fields") or {})
        )
        fields.update(_vat_visual_facts(parse_result))
        if fields:
            line_items = list((solution.canonical_model or {}).get("line_items") or [])
            summary = dict((solution.canonical_model or {}).get("summary") or {})
            issues = [*_solution_issues(solution), *(f"warning:{warning}" for warning in canonical_warnings)]
            field_provenance = _build_field_provenance(parse_result, fields)
            dec = DomainExtractionResult(
                document_type=self.domain_name,
                properties={},
                entities=fields,
                structured_data={
                    "records": [],
                    "line_items": line_items,
                    "sections": [],
                    "tables": [
                        {
                            "table_id": "vat_invoice_line_items",
                            "title": "发票明细",
                            "row_count": len(line_items),
                        }
                    ]
                    if line_items
                    else [],
                    "summary": summary or {"total_rows": len(line_items)},
                    "field_metadata": field_provenance,
                },
                quality=DomainQuality(
                    validation_passed=solution.status == "success",
                    issues=issues,
                    confidence=solution.confidence,
                ),
                metadata={
                    "solver": {
                        "name": "vat_invoice_text_solver_p0",
                        "status": solution.status,
                        "confidence": solution.confidence,
                        "invariants": list(solution.invariant_results),
                    },
                    "field_provenance": field_provenance,
                    "field_provenance_status": _field_provenance_status(parse_result, fields, field_provenance),
                    "extract_status": "ok" if solution.status == "success" else solution.status,
                },
            )
            file_path = getattr(parse_result, "file_path", "") or ""
            ctx = EditionContext(
                edition="community",
                detected_type=self.domain_name,
                full_text=text,
                document_name=Path(file_path).name if file_path else self.display_name,
                page_count=len(getattr(parse_result, "pages", []) or []),
                archetype="key_value_document",
                domain=self.domain_name,
                match_method="vat_invoice_semantic_solver",
                plugin_name=self.domain_name,
                plugin_display_name=self.display_name,
                plugin_version="community-2.0",
                support_level="L1",
                parser_label="docmirror-community",
                source_format="image" if _is_image_parse(parse_result) else "pdf",
            )
            return enrich_vat_invoice_output(edition_serializer(dec, context=ctx))

        out = extract_kv_community_output(
            self,
            parse_result,
            identity_specs=self.identity_fields,
            full_text=text,
        )
        return enrich_vat_invoice_output(out)

    def recognize_facts(self, parse_result, text: str = "") -> FactPatch:
        """Run the VAT semantic solver and return facts without an edition."""
        from docmirror.plugins._base.kv_community_extract import extract_kv_fact_patch
        from docmirror.plugins.vat_invoice.semantic_solver import VATInvoiceSemanticSolver

        solution = VATInvoiceSemanticSolver().solve(full_text=text, parse_result=parse_result)
        fields, canonical_warnings = _canonicalize_vat_fields(
            dict((solution.canonical_model or {}).get("fields") or {})
        )
        fields.update(_vat_visual_facts(parse_result))
        if not fields:
            return extract_kv_fact_patch(
                self,
                parse_result,
                identity_specs=self.identity_fields,
                full_text=text,
            )

        line_items = [
            {
                **dict(item),
                "record_id": str(item.get("record_id") or f"line_items:r{index:06d}"),
            }
            for index, item in enumerate((solution.canonical_model or {}).get("line_items") or [], start=1)
            if isinstance(item, dict)
        ]
        field_details = _build_field_provenance(parse_result, fields)
        warnings = [
            *canonical_warnings,
            *(issue.split(":", 1)[-1] for issue in _solution_issues(solution)),
        ]
        return FactPatch(
            provider_id=self.domain_name,
            document_type=self.domain_name,
            entity_fields={"document_date": fields["invoice_date"]} if fields.get("invoice_date") else {},
            domain_facts={
                **fields,
                "field_details": field_details,
                "summary": dict((solution.canonical_model or {}).get("summary") or {}),
            },
            datasets={"line_items": line_items} if line_items else {},
            warnings=tuple(dict.fromkeys(str(item) for item in warnings if str(item))),
            confidence=float(solution.confidence),
            reason="native VAT semantic facts",
        )


def _solution_issues(solution) -> list[str]:
    issues: list[str] = []
    if solution.status != "success":
        issues.append(f"warning:vat_solver_status:{solution.status}")
    for invariant in solution.invariant_results:
        status = invariant.get("status")
        invariant_id = invariant.get("id")
        if status == "fail":
            prefix = "error" if invariant.get("required") else "warning"
            issues.append(f"{prefix}:{invariant_id}")
        elif status == "warn":
            issues.append(f"warning:{invariant_id}")
    if solution.confidence < 0.9:
        issues.append(f"warning:vat_field_coverage:{solution.confidence:.2f}")
    return issues


def _canonicalize_vat_fields(fields: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Expose one public invoice date without silently hiding conflicts."""
    out = dict(fields)
    warnings: list[str] = []
    issue_date = out.pop("issue_date", None)
    invoice_date = out.get("invoice_date")
    if issue_date not in (None, ""):
        if invoice_date not in (None, "") and invoice_date != issue_date:
            warnings.append("vat_invoice_date_conflict")
        else:
            out["invoice_date"] = issue_date
    return out, warnings


def _is_image_parse(parse_result) -> bool:
    provenance = getattr(parse_result, "provenance", None)
    mime = str(getattr(provenance, "mime_type", "") or "")
    return mime.startswith("image/")


def _vat_visual_facts(parse_result) -> dict[str, Any]:
    """Decode first-page QR data and verify the visible seller seal locally."""
    file_path = str(getattr(parse_result, "file_path", "") or "")
    if not file_path:
        return {}
    try:
        import cv2
        import numpy as np

        if file_path.lower().endswith(".pdf"):
            import fitz

            with fitz.open(file_path) as document:
                if not document:
                    return {}
                pixmap = document[0].get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
                rgb = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
                    pixmap.height,
                    pixmap.width,
                    pixmap.n,
                )
                image = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        else:
            image = cv2.imread(file_path)
        if image is None:
            return {}
        height, width = image.shape[:2]
        detector = cv2.QRCodeDetector()
        qr_value = ""
        qr_points = None
        qr_candidates = (
            image[: max(int(height * 0.35), 1), : max(int(width * 0.35), 1)],
            image,
            cv2.resize(image, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_NEAREST),
        )
        for candidate in qr_candidates:
            qr_value, qr_points, _ = detector.detectAndDecode(candidate)
            if qr_points is not None:
                break
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        red = cv2.bitwise_or(
            cv2.inRange(hsv, np.array([0, 70, 50]), np.array([15, 255, 255])),
            cv2.inRange(hsv, np.array([160, 70, 50]), np.array([180, 255, 255])),
        )
        bottom_red = int((red[int(height * 0.55) :] > 0).sum())
        facts: dict[str, Any] = {
            "qr_code_present": qr_points is not None,
            "qr_code_decoded": bool(qr_value),
            "seller_seal_present": bottom_red >= max(int(width * height * 0.0005), 100),
        }
        if qr_value:
            facts["qr_code_value"] = qr_value
        return facts
    except Exception:
        return {}


def _field_provenance_status(
    parse_result,
    fields: dict[str, Any] | None = None,
    field_provenance: dict[str, Any] | None = None,
) -> dict[str, object]:
    text_blocks = [
        text
        for page in getattr(parse_result, "pages", []) or []
        for text in getattr(page, "texts", []) or []
        if getattr(text, "content", "")
    ]
    with_bbox = [text for text in text_blocks if getattr(text, "bbox", None)]
    field_count = len(fields or {})
    matched_count = len(field_provenance or {})
    return {
        "source": "ocr_text_blocks",
        "text_block_count": len(text_blocks),
        "bbox_text_block_count": len(with_bbox),
        "field_count": field_count,
        "matched_field_count": matched_count,
        "field_level_bbox": bool(field_count and matched_count == field_count),
        "reason": "field_span_alignment_complete"
        if field_count and matched_count == field_count
        else "field_span_alignment_partial",
    }


def _build_field_provenance(parse_result, fields: dict[str, Any]) -> dict[str, Any]:
    lines = _ocr_text_lines(parse_result)
    if not lines:
        return {}
    out: dict[str, Any] = {}
    for field_name, value in fields.items():
        if value in (None, ""):
            continue
        variants = _field_value_variants(field_name, str(value))
        match = _best_line_match(lines, variants)
        if match is None:
            continue
        tokens = _field_token_subset(match, str(match.get("matched_variant") or value))
        evidence_ids = [str(token["evidence_id"]) for token in tokens if token.get("evidence_id")]
        bbox = _union_bbox([token.get("bbox") for token in tokens]) or match["bbox"]
        out[field_name] = {
            "source": "ocr_text_line",
            "page": match["page"],
            "bbox": bbox,
            "line_bbox": match["bbox"],
            "evidence_ids": evidence_ids or match["evidence_ids"],
            "token_match": "token_subset" if evidence_ids else "line_tokens",
            "text": match["text"],
            "confidence": match["confidence"],
            "match": "normalized_substring",
            "value": value,
        }
    return out


def _ocr_text_lines(parse_result) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for page_index, page in enumerate(getattr(parse_result, "pages", []) or [], start=1):
        page_number = int(getattr(page, "page_number", 0) or page_index)
        if page_number <= 0:
            page_number = page_index
        for text in getattr(page, "texts", []) or []:
            content = str(getattr(text, "content", "") or "").strip()
            bbox = getattr(text, "bbox", None)
            if not content or not bbox:
                continue
            lines.append(
                {
                    "page": page_number,
                    "bbox": [float(value) for value in bbox],
                    "text": content,
                    "normalized_text": _normalize_match_text(content),
                    "confidence": float(getattr(text, "confidence", 0.0) or 0.0),
                    "evidence_ids": list(getattr(text, "evidence_ids", []) or []),
                    "tokens": _ocr_tokens(text),
                }
            )
    return lines


def _best_line_match(lines: list[dict[str, Any]], variants: set[str]) -> dict[str, Any] | None:
    normalized_variants = {_normalize_match_text(value) for value in variants if value}
    normalized_variants = {value for value in normalized_variants if value}
    if not normalized_variants:
        return None
    matches: list[tuple[int, float, dict[str, Any], str]] = []
    for line in lines:
        line_text = str(line.get("normalized_text") or "")
        matched_values = [value for value in normalized_variants if value in line_text]
        if matched_values:
            best_value = max(matched_values, key=len)
            matches.append((len(best_value), float(line.get("confidence") or 0.0), line, best_value))
    if not matches:
        return None
    best = max(matches, key=lambda item: (item[0], item[1]))
    return {**best[2], "matched_variant": best[3]}


def _field_value_variants(field_name: str, value: str) -> set[str]:
    variants = {value}
    if field_name in {"issue_date", "invoice_date"} and len(value) == 10 and value[4] == "-" and value[7] == "-":
        variants.add(f"{value[:4]}年{int(value[5:7])}月{int(value[8:10])}日")
        variants.add(f"{value[:4]}年{value[5:7]}月{value[8:10]}日")
    if field_name.endswith("_name"):
        variants.add(value.replace("(", "（").replace(")", "）"))
    if field_name in {"amount_without_tax", "tax_amount", "total_amount"}:
        variants.add(f"¥{value}")
        variants.add(f"￥{value}")
    return variants


def _normalize_match_text(value: str) -> str:
    return (
        str(value or "")
        .replace("：", ":")
        .replace("（", "(")
        .replace("）", ")")
        .replace("￥", "¥")
        .replace(" ", "")
        .replace("\t", "")
        .strip()
    )


def _ocr_tokens(text_block) -> list[dict[str, Any]]:
    slm_entities = getattr(text_block, "slm_entities", None)
    if not isinstance(slm_entities, dict):
        return []
    tokens = slm_entities.get("ocr_tokens")
    if not isinstance(tokens, list):
        return []
    out: list[dict[str, Any]] = []
    for token in tokens:
        if not isinstance(token, dict):
            continue
        bbox = _valid_bbox(token.get("bbox"))
        text = str(token.get("text") or "").strip()
        evidence_id = str(token.get("evidence_id") or "").strip()
        if text and evidence_id:
            out.append({"text": text, "bbox": bbox, "evidence_id": evidence_id})
    return out


def _field_token_subset(line: dict[str, Any], matched_variant: str) -> list[dict[str, Any]]:
    tokens = [token for token in line.get("tokens") or [] if isinstance(token, dict)]
    if not tokens:
        return []
    target = _normalize_match_text(matched_variant)
    if not target:
        return []
    direct = [token for token in tokens if target in _normalize_match_text(str(token.get("text") or ""))]
    if direct:
        return direct
    contained = [token for token in tokens if _normalize_match_text(str(token.get("text") or "")) in target]
    return [token for token in contained if _normalize_match_text(str(token.get("text") or ""))]


def _union_bbox(values: list[Any]) -> list[float] | None:
    boxes = [_valid_bbox(value) for value in values]
    boxes = [box for box in boxes if box]
    if not boxes:
        return None
    return [
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    ]


def _valid_bbox(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 4:
        return None
    try:
        x0, y0, x1, y1 = [float(value[idx]) for idx in range(4)]
    except (TypeError, ValueError):
        return None
    if x1 <= x0 or y1 <= y0:
        return None
    return [x0, y0, x1, y1]


plugin = VATInvoicePlugin()
