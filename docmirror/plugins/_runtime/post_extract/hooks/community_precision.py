# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Conservative precision checks for Community core domain outputs.

The hook never mutates Core Mirror facts or removes edition records. It only
adds stable ``precision:`` warnings when already-extracted facts are incomplete,
malformed, duplicated, or fail a domain invariant. The downstream Community
business projection turns those warnings into ``needs_review`` readiness.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from docmirror.models.entities.parse_result import ParseResult
from docmirror.ocr.correction.validators import validate_uscc
from docmirror.plugins._runtime.post_extract.base import PostExtractHook

_COMMUNITY_PRECISION_DOMAINS = frozenset(
    {
        "bank_statement",
        "wechat_payment",
        "alipay_payment",
        "vat_invoice",
        "business_license",
        "credit_report",
    }
)
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)?$")
_PERSON_ID_RE = re.compile(r"^(?:\d{15}|\d{17}[\dX])$")


def _plain(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    for key in ("normalized_value", "normalized", "value", "raw_value", "raw"):
        if value.get(key) not in (None, ""):
            return value[key]
    return None


def _present(value: Any) -> bool:
    value = _plain(value)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _row_value(record: Any, *keys: str) -> Any:
    if not isinstance(record, dict):
        return None
    normalized = record.get("normalized") if isinstance(record.get("normalized"), dict) else {}
    raw = record.get("raw") if isinstance(record.get("raw"), dict) else {}
    for source in (normalized, raw, record):
        for key in keys:
            if _present(source.get(key)):
                return _plain(source[key])
    return None


def _append_warning(output: dict[str, Any], warning: str) -> None:
    warnings = output.setdefault("status", {}).setdefault("warnings", [])
    if warning not in warnings:
        warnings.append(warning)


def _source_text(result: ParseResult) -> str:
    return str(getattr(result, "extractor_full_text", "") or getattr(result, "full_text", "") or "")


def _domain_name(document_type: str, output: dict[str, Any]) -> str:
    plugin_name = str((output.get("plugin") or {}).get("name") or "")
    domain = plugin_name or document_type
    return "bank_statement" if domain == "bank_reconciliation" else domain


def _precision_bank(output: dict[str, Any]) -> None:
    status = output.get("status") if isinstance(output.get("status"), dict) else {}
    existing = [*(status.get("warnings") or []), *(status.get("errors") or [])]
    for item in existing:
        warning = str(item)
        if warning.startswith("bank_invariant_failed:"):
            _append_warning(output, f"precision:invariant_failed:{warning}")
        elif warning in {"cqf_degraded", "cqf_low_coverage"}:
            _append_warning(output, f"precision:invariant_failed:{warning}")


def _precision_payment(output: dict[str, Any], domain: str) -> None:
    data = output.get("data") if isinstance(output.get("data"), dict) else {}
    records = data.get("records") if isinstance(data.get("records"), list) else []
    if not records:
        _append_warning(output, "precision:missing_required:records")
        return

    aliases = {
        "trade_no": ("trade_no", "transaction_id", "交易单号", "交易订单号"),
        "timestamp": ("timestamp", "date", "交易时间", "交易日期"),
        "amount": ("amount", "amount_cny", "金额", "金额(元)", "交易金额"),
    }
    for field, keys in aliases.items():
        present = sum(1 for record in records if _present(_row_value(record, *keys)))
        coverage = present / len(records)
        if coverage < 0.995:
            _append_warning(
                output,
                f"precision:missing_required_record_field:{field}:coverage={coverage:.4f}",
            )

    timestamps = [_row_value(record, *aliases["timestamp"]) for record in records]
    normalized_timestamps = sum(
        1 for value in timestamps if isinstance(value, str) and bool(_ISO_DATE_RE.fullmatch(value.strip()))
    )
    if normalized_timestamps / len(records) < 0.995:
        _append_warning(output, "precision:normalization_failed:timestamp")

    amounts = [_row_value(record, *aliases["amount"]) for record in records]
    normalized_amounts = sum(1 for value in amounts if isinstance(value, (int, float)) and not isinstance(value, bool))
    if normalized_amounts / len(records) < 0.999:
        _append_warning(output, "precision:normalization_failed:amount")

    seen: set[str] = set()
    duplicates: set[str] = set()
    for record in records:
        trade_no = str(_row_value(record, *aliases["trade_no"]) or "").strip()
        if len(trade_no) < 6:
            continue
        if trade_no in seen:
            duplicates.add(trade_no)
        seen.add(trade_no)
    if duplicates:
        _append_warning(output, f"precision:duplicate_record:{domain}:trade_no")


def _precision_business_license(output: dict[str, Any]) -> None:
    data = output.get("data") if isinstance(output.get("data"), dict) else {}
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    uscc = re.sub(r"[^0-9A-Z]", "", str(_plain(fields.get("unified_social_credit_code")) or "").upper())
    if uscc and not validate_uscc(uscc):
        _append_warning(output, "precision:invalid_format:unified_social_credit_code")


def _money(value: Any) -> Decimal | None:
    raw = str(_plain(value) or "").strip().replace(",", "").replace("，", "")
    raw = re.sub(r"^[¥￥]", "", raw)
    if not raw:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def _precision_vat(result: ParseResult, output: dict[str, Any]) -> None:
    data = output.get("data") if isinstance(output.get("data"), dict) else {}
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    for field in ("invoice_number", "total_amount"):
        if not _present(fields.get(field)):
            _append_warning(output, f"precision:missing_required:{field}")
    if "发票代码" in _source_text(result) and not _present(fields.get("invoice_code")):
        _append_warning(output, "precision:missing_required:invoice_code")

    amount = _money(fields.get("amount_without_tax"))
    tax = _money(fields.get("tax_amount"))
    total = _money(fields.get("total_amount"))
    if amount is not None and tax is not None and total is not None:
        if abs(amount + tax - total) > Decimal("0.01"):
            _append_warning(output, "precision:invariant_failed:vat_amount_equation")


def _repayment_grid_id(record: dict[str, Any]) -> str:
    refs = record.get("source_cell_refs") if isinstance(record.get("source_cell_refs"), list) else []
    first_ref = refs[0] if refs and isinstance(refs[0], dict) else {}
    return str(first_ref.get("grid_id") or record.get("grid_id") or record.get("account_id") or "")


def _duplicate_business_ids(records: Any, id_key: str) -> bool:
    if not isinstance(records, list):
        return False
    seen: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        record_id = str(record.get(id_key) or "").strip()
        if not record_id:
            continue
        if record_id in seen:
            return True
        seen.add(record_id)
    return False


def _precision_credit(output: dict[str, Any]) -> None:
    data = output.get("data") if isinstance(output.get("data"), dict) else {}
    audit = data.get("credit_extraction_audit") if isinstance(data.get("credit_extraction_audit"), dict) else {}
    audit_issues = [str(item) for item in audit.get("issues") or []]
    if audit.get("document_complete") is False or "document_truncated" in audit_issues:
        _append_warning(output, "precision:document_truncated")
    for issue in audit_issues:
        if issue.startswith("missing_evidence:"):
            _append_warning(output, f"precision:{issue}")
        elif issue.startswith("reconciliation_failed:"):
            _append_warning(output, f"precision:invariant_failed:{issue}")
    if audit.get("conflicts"):
        _append_warning(output, "precision:candidate_conflicts")
    if audit.get("quarantined_fields"):
        _append_warning(output, "precision:quarantined_fields")

    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    subtype = str(_plain(fields.get("report_subtype")) or "")
    required = ("subject_name",) if subtype == "enterprise" else ("subject_name", "id_number")
    for field in required:
        if not _present(fields.get(field)):
            _append_warning(output, f"precision:missing_required:{field}")

    if subtype == "enterprise":
        uscc = re.sub(
            r"[^0-9A-Z]",
            "",
            str(_plain(fields.get("unified_social_credit_code")) or "").upper(),
        )
        zhongzheng_code = re.sub(r"\D", "", str(_plain(fields.get("zhongzheng_code")) or ""))
        if not uscc and not zhongzheng_code:
            _append_warning(output, "precision:missing_required:enterprise_identifier")
        if uscc and not validate_uscc(uscc):
            _append_warning(output, "precision:invalid_format:unified_social_credit_code")

    raw_id = str(_plain(fields.get("id_number")) or "").upper().replace(" ", "")
    if raw_id and "*" not in raw_id and not _PERSON_ID_RE.fullmatch(raw_id):
        _append_warning(output, "precision:invalid_format:id_number")

    accounts = data.get("credit_accounts") if isinstance(data.get("credit_accounts"), list) else []
    if _duplicate_business_ids(accounts, "account_id"):
        _append_warning(output, "precision:duplicate_record:credit_account")
    for account in accounts:
        if not isinstance(account, dict):
            continue
        open_date = str(_plain(account.get("open_date")) or "").strip()
        if open_date and not _ISO_DATE_RE.fullmatch(open_date):
            _append_warning(output, "precision:invalid_format:credit_account_open_date")
            break

    inquiries = data.get("inquiry_records") if isinstance(data.get("inquiry_records"), list) else []
    if _duplicate_business_ids(inquiries, "inquiry_id"):
        _append_warning(output, "precision:duplicate_record:credit_inquiry")
    for inquiry in inquiries:
        if not isinstance(inquiry, dict):
            continue
        inquiry_date = str(inquiry.get("inquiry_date") or "").strip()
        if not _ISO_DATE_RE.fullmatch(inquiry_date):
            _append_warning(output, "precision:invalid_format:credit_inquiry_date")
        for field in ("institution", "reason"):
            if not _present(inquiry.get(field)):
                _append_warning(output, f"precision:missing_required_record_field:credit_inquiry:{field}")

    credit_summary = data.get("credit_summary") if isinstance(data.get("credit_summary"), dict) else {}
    projected_account_count = credit_summary.get("projected_account_count")
    if projected_account_count is not None:
        try:
            summary_count = int(projected_account_count)
        except (TypeError, ValueError):
            _append_warning(output, "precision:invalid_format:credit_summary_account_count")
        else:
            if summary_count != len(accounts):
                _append_warning(output, "precision:invariant_failed:credit_account_count")

    for records_name, id_key in (
        ("credit_lines", "credit_line_id"),
        ("overdue_records", "overdue_id"),
        ("public_records", "public_record_id"),
    ):
        if _duplicate_business_ids(data.get(records_name), id_key):
            _append_warning(output, f"precision:duplicate_record:{records_name}")

    records = data.get("repayment_records") if isinstance(data.get("repayment_records"), list) else []
    seen: dict[tuple[str, int, int], str] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        try:
            year = int(record.get("year") or 0)
            month = int(record.get("month") or 0)
        except (TypeError, ValueError):
            _append_warning(output, "precision:invalid_format:repayment_period")
            continue
        if not 1 <= month <= 12:
            _append_warning(output, "precision:invalid_format:repayment_month")
        grid_id = _repayment_grid_id(record)
        if not grid_id:
            _append_warning(output, "precision:missing_evidence:repayment_account_anchor")
        key = (grid_id, year, month)
        status = str(record.get("status") or "")
        if key in seen:
            reason = "conflicting_repayment_status" if seen[key] != status else "repayment_month"
            _append_warning(output, f"precision:duplicate_record:{reason}")
        else:
            seen[key] = status


class CommunityPrecisionHook(PostExtractHook):
    """Add conservative domain precision warnings to Community outputs."""

    hook_id = "community_precision"

    def apply(
        self,
        result: ParseResult,
        *,
        extracted: dict[str, Any],
        edition: str,
        document_type: str,
        plugin: Any | None = None,
    ) -> None:
        del plugin
        if edition != "community":
            return
        domain = _domain_name(document_type, extracted)
        if domain not in _COMMUNITY_PRECISION_DOMAINS:
            return
        if domain == "bank_statement":
            _precision_bank(extracted)
        elif domain in {"wechat_payment", "alipay_payment"}:
            _precision_payment(extracted, domain)
        elif domain == "business_license":
            _precision_business_license(extracted)
        elif domain == "vat_invoice":
            _precision_vat(result, extracted)
        elif domain == "credit_report":
            _precision_credit(extracted)


__all__ = ["CommunityPrecisionHook"]
