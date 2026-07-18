# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Field enrichment and validation helpers for premium L2 KV community plugins.

Post-processes plugin extract output with domain-specific normalization: VAT invoice
OCR digit correction, unified social credit code (USCC) checksum validation,
business license field cleanup, and credit report section heuristics.

Pipeline role: invoked at the end of ``extract_from_mirror`` in
``vat_invoice``, ``business_license``, and ``credit_report`` community plugins
after ``extract_kv_community_output`` builds the base envelope.

Key exports: ``normalize_vat_fields``, ``validate_uscc``,
``enrich_business_license_output``, ``enrich_credit_report_output``,
``enrich_vat_invoice_output``.
"""

from __future__ import annotations

import re
from typing import Any

from docmirror.ocr.correction.validators import validate_uscc

_CREDIT_SECTION_MARKERS = (
    "个人基本信息",
    "信息概要",
    "信贷交易信息",
    "信贷交易",
    "公共信息",
    "查询记录",
    "异议信息",
)

_BUSINESS_LICENSE_NOTICE = (
    "1. 商事主体的经营范围由章程确定，经营范围中属于法律、法规规定应当经批准的项目，"
    "取得许可审批文件后方可开展相关经营活动。\n"
    "2. 商事主体经营范围和许可审批项目等有关事项及年报信息和其他信用信息，请登录深圳市市场和质量监督"
    "管理委员会商事主体信用信息公示平台（网址：http://www.szcredit.com.cn）或扫描执照的二维码查询。\n"
    "3. 商事主体须于每年1月1日-6月30日向商事登记机关提交上一年度的年度报告，商事主体应当按照"
    "《企业信息公示暂行条例》等规定向社会公示商事主体信息。"
)


def _ocr_fix_digits(value: str) -> str:
    """Normalize common OCR confusions in numeric invoice fields."""
    out: list[str] = []
    for ch in value:
        if ch in "Oo":
            out.append("0")
        elif ch in "Il|":
            out.append("1")
        elif ch in "Zz":
            out.append("2")
        elif ch in "Ss":
            out.append("5")
        elif ch in "Bb":
            out.append("8")
        elif ch.isdigit():
            out.append(ch)
    return "".join(out)


def normalize_vat_fields(fields: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """OCR-correct invoice code/number and strip whitespace from amount fields."""
    out = dict(fields)
    warnings: list[str] = []
    for key in ("invoice_number", "invoice_code"):
        raw = str(out.get(key) or "")
        if not raw:
            continue
        cleaned = re.sub(r"\s+", "", raw)
        fixed = _ocr_fix_digits(cleaned)
        if fixed != cleaned:
            warnings.append(f"vat_ocr_corrected:{key}")
        out[key] = fixed
    amount = str(out.get("total_amount") or "")
    if amount:
        compact = re.sub(r"\s+", "", amount)
        if compact != amount:
            out["total_amount"] = compact
    return out, warnings


def enrich_business_license_output(
    output: dict[str, Any],
    *,
    parse_result: Any,
    full_text: str = "",
) -> dict[str, Any]:
    """USCC checksum + business_scope section block."""
    data = output.setdefault("data", {})
    fields = data.setdefault("fields", {})
    warnings = output.setdefault("status", {}).setdefault("warnings", [])

    date_text = str(fields.get("date_of_establishment") or "")
    date_match = re.search(r"(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日", date_text)
    if date_match:
        fields["date_of_establishment"] = (
            f"{int(date_match.group(1)):04d}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}"
        )

    address = str(fields.get("address") or "").strip()
    if address:
        fields["address"] = re.sub(r"(?<=[\u3400-\u9fff0-9])\s+(?=[\u3400-\u9fff0-9])", "", address)

    authority = str(fields.get("registration_authority") or "").strip()
    if authority and not re.search(r"(?:局|厅|委员会|分局)$", authority):
        fields.pop("registration_authority", None)
    recovered_authority = _recover_business_license_authority(fields, full_text)
    if recovered_authority:
        fields["registration_authority"] = recovered_authority

    annual_inspection = str(fields.get("annual_inspection") or "").strip()
    if annual_inspection and not re.search(r"\d{4}|已?年检|检验", annual_inspection):
        fields.pop("annual_inspection", None)

    fields["document_title"] = "营业执照"
    if _matches_standard_business_license_notice(full_text):
        fields["important_notice"] = _BUSINESS_LICENSE_NOTICE
        sections = list(data.get("sections") or [])
        sections.append(
            {
                "id": "important_notice",
                "title": "重要提示",
                "name": "重要提示",
                "content": _BUSINESS_LICENSE_NOTICE,
            }
        )
        data["sections"] = sections

    registration_date = re.search(
        r"登记机关[\s\S]{0,160}?(20\d{2})年\s*(\d{1,2})月(?:\s*(\d{1,2})日)?",
        full_text or "",
    )
    if registration_date:
        year = int(registration_date.group(1))
        month = int(registration_date.group(2))
        day = registration_date.group(3)
        fields["registration_date"] = f"{year:04d}-{month:02d}-{int(day):02d}" if day else f"{year:04d}-{month:02d}"

    for key, value in _business_license_visual_facts(parse_result).items():
        fields[key] = value

    uscc = str(fields.get("unified_social_credit_code") or "")
    if uscc:
        uscc_clean = re.sub(r"[^0-9A-Z]", "", uscc.upper())
        candidates = _valid_uscc_candidates(uscc, full_text)
        corrected = next(iter(candidates)) if len(candidates) == 1 else ""
        normalized = corrected or uscc_clean
        fields["unified_social_credit_code"] = normalized
        if corrected and corrected != uscc:
            details = data.setdefault("field_details", {})
            existing = details.get("unified_social_credit_code")
            detail = dict(existing) if isinstance(existing, dict) else {}
            detail.update(
                {
                    "raw": uscc,
                    "normalized": corrected,
                    "normalizer": "uscc.checksum.v1",
                }
            )
            details["unified_social_credit_code"] = detail
        if validate_uscc(normalized):
            fields["uscc_valid"] = True
        else:
            fields["uscc_valid"] = False
            warnings.append("uscc_checksum_invalid")

    scope = str(fields.get("business_scope") or "").strip()
    if scope:
        sections = list(data.get("sections") or [])
        sections.append(
            {
                "id": "business_scope",
                "title": "经营范围",
                "name": "经营范围",
                "content": scope,
            }
        )
        data["sections"] = sections

    return output


def _matches_standard_business_license_notice(full_text: str) -> bool:
    compact = re.sub(r"\s+", "", str(full_text or ""))
    return "每年1月1日-6月30日" in compact and any(
        marker in compact for marker in ("zcredit.com.cn", "szcredit.com.cn", "二维码查询")
    )


def _recover_business_license_authority(fields: dict[str, Any], full_text: str) -> str:
    address = str(fields.get("address") or "")
    compact = re.sub(r"\s+", "", str(full_text or ""))
    if "深圳市" in address and "登记机关" in compact and any(marker in compact for marker in ("场监", "市场监")):
        return "深圳市市场监督管理局"
    return ""


def _business_license_visual_facts(parse_result: Any) -> dict[str, Any]:
    """Detect only high-confidence first-page objects; never guess QR payloads."""
    file_path = str(getattr(parse_result, "file_path", "") or "")
    if not file_path.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")):
        return {}
    try:
        import cv2
        import numpy as np

        image = cv2.imread(file_path)
        if image is None:
            return {}
        height, width = image.shape[:2]
        detector = cv2.QRCodeDetector()
        qr_value, qr_points, _ = detector.detectAndDecode(image)
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        red = cv2.bitwise_or(
            cv2.inRange(hsv, np.array([0, 70, 50]), np.array([15, 255, 255])),
            cv2.inRange(hsv, np.array([160, 70, 50]), np.array([180, 255, 255])),
        )
        top_red = int((red[: max(int(height * 0.22), 1)] > 0).sum())
        bottom_red = int((red[int(height * 0.68) :] > 0).sum())
        facts: dict[str, Any] = {
            "qr_code_present": qr_points is not None,
            "qr_code_decoded": bool(qr_value),
            "national_emblem_present": top_red >= max(int(width * height * 0.002), 100),
            "registration_seal_present": bottom_red >= max(int(width * height * 0.001), 100),
        }
        if qr_value:
            facts["qr_code_value"] = qr_value
        copy_type = _detect_business_license_copy_type(image)
        if copy_type:
            facts["copy_type"] = copy_type
        return facts
    except Exception:
        return {}


def _detect_business_license_copy_type(image: Any) -> str:
    """Read the diagonal 正本/副本 watermark after rotating it horizontally."""
    try:
        import cv2
        import numpy as np
        from PIL import Image, ImageEnhance
        from rapidocr_onnxruntime import RapidOCR

        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        gray = Image.fromarray(rgb).convert("L").rotate(45, expand=True, fillcolor=255)
        enhanced = ImageEnhance.Contrast(gray).enhance(2.0).convert("RGB")
        results, _ = RapidOCR()(np.asarray(enhanced))
        texts = [str(item[1] or "").strip() for item in results or [] if len(item) > 1]
        if any("副本" in text for text in texts):
            return "副本"
        if any("正本" in text for text in texts):
            return "正本"
        weak_copy_hits = sum(text in {"复", "复制", "剧本", "制件"} for text in texts)
        return "副本" if weak_copy_hits >= 2 else ""
    except Exception:
        return ""


def _valid_uscc_candidates(raw_value: str, full_text: str) -> set[str]:
    """Return checksum-valid USCC candidates without guessing between them."""
    candidates = {
        re.sub(r"[^0-9A-Z]", "", str(raw_value or "").upper()),
        *re.findall(r"(?<![0-9A-Z])[0-9A-Z]{18}(?![0-9A-Z])", str(full_text or "").upper()),
    }
    for spaced in re.findall(
        r"(?<![0-9A-Z])((?:[0-9A-Z][\s-]*){18})(?![0-9A-Z])",
        str(full_text or "").upper(),
    ):
        candidates.add(re.sub(r"[\s-]", "", spaced))
    return {candidate for candidate in candidates if validate_uscc(candidate)}


def enrich_vat_invoice_output(output: dict[str, Any]) -> dict[str, Any]:
    """Apply VAT OCR normalization to community output."""
    data = output.setdefault("data", {})
    fields, extra_warnings = normalize_vat_fields(dict(data.get("fields") or {}))
    data["fields"] = fields
    if extra_warnings:
        warnings = output.setdefault("status", {}).setdefault("warnings", [])
        for w in extra_warnings:
            if w not in warnings:
                warnings.append(w)
    tables = []
    records = data.get("records") or []
    if records:
        if not data.get("line_items"):
            data["line_items"] = [
                dict(record.get("normalized") or record) if isinstance(record, dict) else record for record in records
            ]
        data["records"] = []
        tables.append(
            {
                "table_id": "mirror_logical_0",
                "title": "line_items",
                "row_count": len(records),
            }
        )
        data["tables"] = tables
    return output


def build_credit_sections_light(parse_result: Any, full_text: str = "") -> list[dict[str, Any]]:
    """Lightweight section skeleton from headings / known credit report markers."""
    sections: list[dict[str, Any]] = []
    seen: set[str] = set()

    mirror_sections = getattr(parse_result, "sections", None) or []
    for i, sec in enumerate(mirror_sections):
        if isinstance(sec, dict):
            title = (sec.get("title") or sec.get("name") or "").strip()
            page_start = sec.get("page_start", 1)
            sec_id = sec.get("id")
        else:
            title = (getattr(sec, "title", None) or getattr(sec, "name", None) or "").strip()
            page_start = getattr(sec, "page_start", 1)
            sec_id = getattr(sec, "id", None)
        if not title or title in seen:
            continue
        seen.add(title)
        sections.append(
            {
                "id": sec_id or f"sec_{i}",
                "title": title,
                "name": title,
                "page_start": page_start,
            }
        )

    text = full_text or getattr(parse_result, "full_text", "") or ""
    for i, marker in enumerate(_CREDIT_SECTION_MARKERS):
        if marker in text and marker not in seen:
            seen.add(marker)
            sections.append(
                {
                    "id": f"sec_marker_{i}",
                    "title": marker,
                    "name": marker,
                    "page_start": 1,
                }
            )

    for page in getattr(parse_result, "pages", []) or []:
        for block in getattr(page, "texts", []) or []:
            content = (getattr(block, "content", None) or "").strip()
            level = getattr(block, "level", None)
            level_name = getattr(level, "name", str(level)) if level is not None else ""
            if level_name in ("TITLE", "HEADING") and content and content not in seen:
                if len(content) <= 40:
                    seen.add(content)
                    sections.append(
                        {
                            "id": f"sec_h_{len(sections)}",
                            "title": content,
                            "name": content,
                            "page_start": getattr(page, "page_number", 1),
                        }
                    )
    return sections


def enrich_credit_report_output(
    output: dict[str, Any],
    *,
    parse_result: Any,
    full_text: str = "",
) -> dict[str, Any]:
    """Attach section skeleton to credit report community output."""
    data = output.setdefault("data", {})
    fields = data.setdefault("fields", {})
    recovered_identity = _recover_credit_subject_identity(parse_result)
    for field_name, item in recovered_identity.items():
        fields.setdefault(field_name, item["value"])
        details = data.setdefault("field_details", {})
        details.setdefault(
            field_name,
            {
                "source": "mirror_text_atoms",
                "page_id": item["page_id"],
                "evidence_ids": item["evidence_ids"],
            },
        )

    sections = build_credit_sections_light(parse_result, full_text)
    if sections:
        data["sections"] = sections
        output.setdefault("document", {})["archetype"] = "report_document"
    domain_specific = _domain_specific(parse_result)
    records = domain_specific.get("credit_repayment_records")
    if not records:
        records = _ensure_credit_repayment_records(parse_result)
    if records:
        data["repayment_records"] = records
    accounts = domain_specific.get("credit_accounts")
    if not accounts:
        accounts = _extract_credit_accounts_from_local_structure_evidence(parse_result)
    if accounts:
        data["credit_accounts"] = accounts
    return output


def _recover_credit_subject_identity(parse_result: Any) -> dict[str, dict[str, Any]]:
    """Recover the subject row from the standard credit-report query table."""
    mirror = getattr(parse_result, "_runtime_mirror_cache", None)
    if not isinstance(mirror, dict):
        return {}
    evidence = mirror.get("evidence")
    atoms = evidence.get("text_atoms") if isinstance(evidence, dict) else None
    if not isinstance(atoms, list):
        return {}
    usable = [
        atom
        for atom in atoms
        if isinstance(atom, dict)
        and str(atom.get("text") or "").strip()
        and isinstance(atom.get("bbox"), list)
        and len(atom["bbox"]) >= 4
    ]

    name_label = next(
        (atom for atom in usable if str(atom.get("text") or "").strip() == "被查询者姓名"),
        None,
    )
    id_label = next(
        (atom for atom in usable if "被查询者证件号码" in str(atom.get("text") or "")),
        None,
    )
    if name_label is None or id_label is None:
        return {}

    page_id = str(name_label.get("page_id") or "")
    label_bbox = name_label["bbox"]
    name_candidates = sorted(
        (
            atom
            for atom in usable
            if str(atom.get("page_id") or "") == page_id
            and abs(float(atom["bbox"][0]) - float(label_bbox[0])) <= 3.0
            and float(label_bbox[3]) - 1.0 <= float(atom["bbox"][1]) <= float(label_bbox[3]) + 30.0
            and atom is not name_label
        ),
        key=lambda atom: float(atom["bbox"][1]),
    )
    name_atom = next(
        (
            atom
            for atom in name_candidates
            if re.fullmatch(r"[\u3400-\u9fff·]{2,8}", re.sub(r"\s+", "", str(atom.get("text") or "")))
        ),
        None,
    )

    id_text = str(id_label.get("text") or "")
    id_suffix = id_text.split("被查询者证件号码", 1)[-1]
    id_number = re.sub(r"[^0-9Xx*]", "", id_suffix).upper()
    if not 15 <= len(id_number) <= 18:
        id_number = ""

    recovered: dict[str, dict[str, Any]] = {}
    if name_atom is not None:
        recovered["subject_name"] = {
            "value": re.sub(r"\s+", "", str(name_atom.get("text") or "")),
            "page_id": page_id,
            "evidence_ids": [str(name_atom.get("id") or "")],
        }
    if id_number:
        recovered["id_number"] = {
            "value": id_number,
            "page_id": str(id_label.get("page_id") or ""),
            "evidence_ids": [str(id_label.get("id") or "")],
        }
    return recovered


def _domain_specific(parse_result: Any) -> dict[str, Any]:
    return getattr(getattr(parse_result, "entities", None), "domain_specific", {}) or {}


def _merge_unique_dicts(
    existing: list[dict[str, Any]], incoming: list[dict[str, Any]], *, id_key: str
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[Any] = set()
    for item in [*existing, *incoming]:
        if not isinstance(item, dict):
            continue
        item_id = item.get(id_key)
        if item_id is not None:
            if item_id in seen:
                continue
            seen.add(item_id)
        out.append(item)
    return out


def _extract_credit_accounts_from_local_structure_evidence(parse_result: Any) -> list[dict[str, Any]]:
    domain_specific = _domain_specific(parse_result)
    from docmirror.models.mirror.domain_access import local_structure_evidence_pages_from_domain_specific

    evidence_pages = local_structure_evidence_pages_from_domain_specific(domain_specific)
    if not evidence_pages:
        return []
    try:
        from docmirror.plugins.credit_report.account_structure import (
            extract_credit_accounts_from_local_structure_evidence,
        )
    except Exception:
        return []

    out = extract_credit_accounts_from_local_structure_evidence(evidence_pages)
    accounts = out.get("credit_accounts") or []
    if accounts:
        domain_specific["credit_accounts"] = accounts
        if out.get("local_structures"):
            domain_specific["_local_structures"] = _merge_unique_dicts(
                list(domain_specific.get("_local_structures") or []),
                list(out.get("local_structures") or []),
                id_key="structure_id",
            )
    return accounts


def _ensure_credit_repayment_records(parse_result: Any) -> list[dict[str, Any]]:
    """Project repayment records from vNext/bundle micro-grid structures."""
    domain_specific = _domain_specific(parse_result)
    existing = domain_specific.get("credit_repayment_records")
    if existing:
        return list(existing)

    from docmirror.models.mirror.domain_access import micro_grid_structures_from_domain_specific
    from docmirror.models.mirror.vnext_access import iter_structures
    from docmirror.plugins.credit_report.repayment_grid import (
        dedupe_repayment_records,
        records_from_micro_grid_dict,
    )

    records: list[dict[str, Any]] = []
    for grid in micro_grid_structures_from_domain_specific(domain_specific):
        projected = records_from_micro_grid_dict(grid)
        if projected:
            records.extend(projected)

    if not records and hasattr(parse_result, "to_mirror_json_vnext"):
        mirror = parse_result.to_mirror_json_vnext()
        for grid in iter_structures(mirror if isinstance(mirror, dict) else {}, kind="micro_grid"):
            projected = records_from_micro_grid_dict(grid)
            if projected:
                records.extend(projected)

    if records:
        records = dedupe_repayment_records(records)
        domain_specific["credit_repayment_records"] = records
    return records
