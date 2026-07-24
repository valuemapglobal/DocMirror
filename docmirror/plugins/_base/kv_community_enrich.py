# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Field enrichment and validation helpers for premium L2 KV community plugins.

Post-processes plugin extract output with domain-specific normalization: VAT invoice
OCR digit correction, unified social credit code (USCC) checksum validation,
business license field cleanup, and credit report section heuristics.

Pipeline role: invoked during post-seal Community projection in ``vat_invoice``,
``business_license``, and ``credit_report`` while constructing edition JSON.

Key exports: ``normalize_vat_fields``, ``validate_uscc``,
``enrich_business_license_output``, ``enrich_credit_report_output``,
``enrich_vat_invoice_output``.
"""

from __future__ import annotations

import re
from typing import Any

from docmirror.ocr.correction.validators import validate_uscc

_CREDIT_SECTION_SPECS: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "personal_brief": (
        ("信息概要", ("信息概要",)),
        ("信贷记录", ("信贷记录",)),
        ("公共记录", ("公共记录", "公共信息")),
        ("查询记录", ("查询记录",)),
        ("说明", ("说明",)),
    ),
    "personal_detail": (
        ("个人基本信息", ("个人基本信息",)),
        ("信息概要", ("信息概要",)),
        ("信贷交易信息明细", ("信贷交易信息明细", "信贷交易信息")),
        ("非信贷交易信息明细", ("非信贷交易信息明细", "非银行信息")),
        ("公共信息明细", ("公共信息明细", "公共信息")),
        ("查询记录", ("查询记录",)),
        ("本人声明", ("本人声明",)),
        ("异议标注", ("异议标注", "异议信息")),
    ),
    "enterprise": (
        ("身份标识", ("身份标识",)),
        ("信息概要", ("信息概要",)),
        ("基本信息", ("基本信息",)),
        ("信贷记录明细", ("信贷记录明细",)),
        ("公共记录明细", ("公共记录明细",)),
        ("信用记录补充信息", ("信用记录补充信息",)),
    ),
}

_CREDIT_SECTION_FALLBACK = (
    ("个人基本信息", ("个人基本信息",)),
    ("信息概要", ("信息概要",)),
    ("信贷交易信息", ("信贷交易信息", "信贷交易")),
    ("公共信息", ("公共信息",)),
    ("查询记录", ("查询记录",)),
    ("异议信息", ("异议信息",)),
)

_CREDIT_NON_INSTITUTION_VALUES = frozenset(
    {
        "信用卡",
        "贷款",
        "其他业务",
        "购房",
        "其他",
        "信息概要",
        "信贷记录",
    }
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
    from docmirror.plugins.credit_report.report_profile import detect_credit_report_subtype

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
    subtype = detect_credit_report_subtype(parse_result, text)
    specs = _CREDIT_SECTION_SPECS.get(subtype, _CREDIT_SECTION_FALLBACK)
    page_texts = _credit_page_texts(parse_result)
    for i, (title, aliases) in enumerate(specs):
        matched_alias = next((alias for alias in aliases if alias in text), "")
        if matched_alias and title not in seen:
            seen.add(title)
            page_start = next(
                (page_number for page_number, page_text in page_texts if matched_alias in page_text),
                1,
            )
            sections.append(
                {
                    "id": f"sec_marker_{i}",
                    "title": title,
                    "name": title,
                    "page_start": page_start,
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


def _credit_page_texts(parse_result: Any) -> list[tuple[int, str]]:
    """Build bounded page text for section page-start lookup."""
    out: list[tuple[int, str]] = []
    for index, page in enumerate(getattr(parse_result, "pages", []) or [], start=1):
        parts = [str(getattr(block, "content", "") or "") for block in getattr(page, "texts", []) or []]
        for kv in getattr(page, "key_values", []) or []:
            parts.extend((str(getattr(kv, "key", "") or ""), str(getattr(kv, "value", "") or "")))
        for table in getattr(page, "tables", []) or []:
            parts.extend(str(header or "") for header in getattr(table, "headers", []) or [])
            for row in getattr(table, "rows", []) or []:
                parts.extend(str(getattr(cell, "text", "") or "") for cell in getattr(row, "cells", []) or [])
        out.append((int(getattr(page, "page_number", 0) or index), "\n".join(parts)))
    return out


def enrich_credit_report_output(
    output: dict[str, Any],
    *,
    parse_result: Any,
    full_text: str = "",
) -> dict[str, Any]:
    """Attach section skeleton to credit report community output."""
    from docmirror.plugins.credit_report.business_assembly import assemble_credit_report_business
    from docmirror.plugins.credit_report.report_profile import (
        detect_credit_report_content_mode,
        detect_credit_report_subtype,
        recover_credit_report_header_fields,
    )
    from docmirror.plugins.credit_report.scanned_business import (
        extract_scanned_credit_business,
        link_repayment_records_to_accounts,
    )

    data = output.setdefault("data", {})
    fields = data.setdefault("fields", {})
    recovered_identity = _recover_credit_subject_identity(parse_result)
    for field_name, item in recovered_identity.items():
        fields.setdefault(field_name, item["value"])
        details = data.setdefault("field_details", {})
        details.setdefault(
            field_name,
            {
                "source": "canonical_evidence_atoms",
                "page_id": item["page_id"],
                "evidence_ids": item["evidence_ids"],
            },
        )

    report_subtype = detect_credit_report_subtype(parse_result, full_text)
    content_mode = detect_credit_report_content_mode(parse_result)
    recovered_header = recover_credit_report_header_fields(
        parse_result,
        full_text,
        report_subtype=report_subtype,
    )
    if report_subtype != "unknown":
        recovered_header.setdefault("report_subtype", report_subtype)
    if content_mode != "unknown":
        recovered_header.setdefault("content_mode", content_mode)
    details = data.setdefault("field_details", {})
    for field_name, value in recovered_header.items():
        # The shared KV matcher may overrun into adjacent labels on dense report
        # covers. Domain-validated header facts intentionally replace those values.
        fields[field_name] = value
        details[field_name] = {
            "source": "credit_report_header",
            "confidence": 0.95 if field_name not in {"report_subtype", "content_mode"} else 1.0,
        }
    query_institution = re.sub(r"\s+", "", str(fields.get("query_institution") or ""))
    if "query_institution" not in recovered_header and query_institution in _CREDIT_NON_INSTITUTION_VALUES:
        fields.pop("query_institution", None)
        details.pop("query_institution", None)

    domain_specific = _domain_specific(parse_result)
    if report_subtype != "unknown":
        domain_specific["report_subtype"] = report_subtype
    if content_mode != "unknown":
        domain_specific["content_mode"] = content_mode
    document = output.setdefault("document", {})
    properties = document.setdefault("properties", {})
    if report_subtype != "unknown":
        properties["report_subtype"] = report_subtype
    if content_mode != "unknown":
        document["content_mode"] = content_mode

    sections = build_credit_sections_light(parse_result, full_text)
    if sections:
        data["sections"] = sections
        document["archetype"] = "report_document"
    from docmirror.plugins.credit_report.source_content import build_credit_source_content

    source_content = build_credit_source_content(parse_result)
    if source_content.get("pages"):
        data["source_content"] = source_content

    scanned_business: dict[str, Any] = {}
    if content_mode in {"scanned_ocr", "mixed"}:
        scanned_business = extract_scanned_credit_business(parse_result, full_text)
        subject_profile = dict(scanned_business.get("subject_profile") or {})
        for profile_key, field_key in (("subject_name", "subject_name"), ("id_number", "id_number")):
            if fields.get(field_key) and profile_key not in subject_profile:
                subject_profile[profile_key] = {
                    "value": fields[field_key],
                    "raw": fields[field_key],
                    "source_refs": [{"source": "credit_report_header"}],
                }
        if subject_profile:
            data["subject_profile"] = subject_profile
        for collection in (
            "residence_records",
            "employment_records",
            "repayment_liability_records",
            "statements",
            "annotations",
        ):
            data[collection] = list(scanned_business.get(collection) or [])

    repayment_records = list(domain_specific.get("credit_repayment_records") or [])
    if not repayment_records and (
        content_mode in {"scanned_ocr", "mixed"} or _has_credit_repayment_structures(parse_result)
    ):
        repayment_records = _ensure_credit_repayment_records(parse_result)
    if repayment_records:
        data["repayment_records"] = repayment_records

    credit_accounts = _canonicalize_credit_accounts(list(scanned_business.get("credit_accounts") or []))
    if not credit_accounts:
        credit_accounts = _canonicalize_credit_accounts(list(domain_specific.get("credit_accounts") or []))
    if not credit_accounts:
        credit_accounts = _canonicalize_credit_accounts(
            _extract_credit_accounts_from_local_structure_evidence(parse_result)
        )

    from docmirror.models.mirror.domain_access import micro_grid_structures_from_domain_specific

    repayment_records = link_repayment_records_to_accounts(
        repayment_records,
        credit_accounts,
        micro_grid_structures_from_domain_specific(domain_specific),
    )

    existing_inquiries = [
        *list(data.get("inquiry_records") or []),
        *list(scanned_business.get("inquiry_records") or []),
    ]
    existing_summary = {
        **dict(data.get("credit_summary") or {}),
        **dict(scanned_business.get("credit_summary") or {}),
    }

    assembled = assemble_credit_report_business(
        parse_result,
        full_text,
        report_subtype=report_subtype,
        content_mode=content_mode,
        existing_collections={
            "credit_accounts": [*list(data.get("credit_accounts") or []), *credit_accounts],
            "credit_lines": list(data.get("credit_lines") or []),
            "repayment_records": repayment_records,
            "overdue_records": list(data.get("overdue_records") or []),
            "inquiry_records": existing_inquiries,
            "public_records": list(data.get("public_records") or []),
        },
        existing_summary=existing_summary,
    )
    for data_key in (
        "credit_accounts",
        "credit_lines",
        "repayment_records",
        "overdue_records",
        "inquiry_records",
        "public_records",
    ):
        records = list(assembled.get(data_key) or [])
        data[data_key] = records
        if records:
            domain_key = "credit_repayment_records" if data_key == "repayment_records" else data_key
            domain_specific[domain_key] = records

    credit_accounts = list(assembled.get("credit_accounts") or [])
    repayment_records = list(assembled.get("repayment_records") or [])
    overdue_records = list(assembled.get("overdue_records") or [])
    credit_summary = assembled.get("credit_summary")
    if isinstance(credit_summary, dict) and credit_summary:
        data["credit_summary"] = credit_summary
    credit_audit = assembled.get("credit_extraction_audit")
    if isinstance(credit_audit, dict):
        # Rebuild after repayment-grid materialization so the Community source
        # view carries every persisted grid and its cell-level provenance.
        source_content = build_credit_source_content(parse_result)
        if source_content.get("pages"):
            data["source_content"] = source_content
            credit_audit["source_conservation"] = dict(source_content.get("conservation_audit") or {})
        data["credit_extraction_audit"] = credit_audit
        domain_specific["credit_extraction_audit"] = credit_audit

    has_business_records = any(
        assembled.get(data_key)
        for data_key in (
            "credit_accounts",
            "credit_lines",
            "repayment_records",
            "overdue_records",
            "inquiry_records",
            "public_records",
        )
    )
    if has_business_records and _only_positional_credit_records(data.get("records")):
        data["records"] = []
    if has_business_records:
        summary = data.setdefault("summary", {})
        summary.update(
            {
                "total_rows": len(credit_accounts),
                "credit_account_count": len(credit_accounts),
                "repayment_record_count": len(repayment_records),
                "overdue_record_count": len(overdue_records),
                "inquiry_record_count": len(data.get("inquiry_records") or []),
            }
        )
    return output


def _only_positional_credit_records(records: Any) -> bool:
    if not isinstance(records, list) or not records:
        return False
    for record in records:
        if not isinstance(record, dict):
            return False
        row = record.get("normalized") or record.get("raw") or record
        if not isinstance(row, dict) or not row:
            return False
        business_keys = {str(key) for key in row if str(key) not in {"row_index", "page"}}
        if not business_keys or not all(re.fullmatch(r"col_\d+", key) for key in business_keys):
            return False
    return True


def _canonicalize_credit_accounts(accounts: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for index, item in enumerate(accounts):
        if not isinstance(item, dict):
            continue
        account = dict(item)
        if not account.get("account_id"):
            anchor = str(account.get("source_structure_id") or account.get("account_identifier") or "").strip()
            account["account_id"] = (
                f"credit_account:{anchor}"
                if anchor
                else f"credit_account:projected:{account.get('page', 0)}:{index + 1}"
            )
        if not account.get("source_refs"):
            ref: dict[str, Any] = {"source": account.get("source") or "credit_account_projection"}
            if account.get("page"):
                ref["page"] = account["page"]
            if account.get("source_structure_id"):
                ref["structure_id"] = account["source_structure_id"]
            account["source_refs"] = [ref]
        out.append(account)
    return out


def _recover_credit_subject_identity(parse_result: Any) -> dict[str, dict[str, Any]]:
    """Recover the subject row from the standard credit-report query table."""
    from docmirror.plugins._runtime.evidence_access import text_atoms

    atoms = text_atoms(parse_result)
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
    value = getattr(getattr(parse_result, "entities", None), "domain_specific", {})
    return value if isinstance(value, dict) else {}


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
    from docmirror.plugins.credit_report.micro_grid_materialize import (
        augment_credit_repayment_evidence_bundles,
        materialize_credit_repayment_micro_grids_from_bundles,
    )
    from docmirror.plugins.credit_report.repayment_grid import (
        dedupe_repayment_records,
        records_from_micro_grid_dict,
    )

    records: list[dict[str, Any]] = []
    augment_credit_repayment_evidence_bundles(domain_specific)
    from docmirror.plugins.credit_report.page_image_resolver import LogicalPageImageResolver

    image_resolver = LogicalPageImageResolver(parse_result)
    try:
        materialize_credit_repayment_micro_grids_from_bundles(
            domain_specific,
            page_image_resolver=image_resolver,
            enable_cell_ocr=True,
        )
    finally:
        image_resolver.clear()
    for grid in micro_grid_structures_from_domain_specific(domain_specific):
        projected = records_from_micro_grid_dict(grid)
        if projected:
            records.extend(projected)

    if records:
        records = dedupe_repayment_records(records)
        domain_specific["credit_repayment_records"] = records
    return records


def _has_credit_repayment_structures(parse_result: Any) -> bool:
    """Check persisted micro-grids without rebuilding the full Mirror view."""
    from docmirror.models.mirror.domain_access import micro_grid_structures_from_domain_specific

    return bool(micro_grid_structures_from_domain_specific(_domain_specific(parse_result)))
