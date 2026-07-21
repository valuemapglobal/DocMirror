# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Consumer-facing business records for public credit-report variants.

Native personal brief reports express accounts as prose and inquiries as a
borderless ledger. Native enterprise reports expose a compact summary followed
by account-history cards. Scanned personal detail reports continue to use the
geometry-aware local-structure and repayment-grid projectors; this module only
derives their overdue view from already-projected records.
"""

from __future__ import annotations

import hashlib
import re
from decimal import Decimal, InvalidOperation
from typing import Any

_DATE_CN_RE = re.compile(r"(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日")
_ACCOUNT_DATE_PATTERN = r"20\d{2}年\s*\d{1,2}月\s*\d{1,2}日"
_ACCOUNT_START_RE = re.compile(
    rf"{_ACCOUNT_DATE_PATTERN}"
    rf"(?=(?:(?!{_ACCOUNT_DATE_PATTERN}).){{4,100}}?(?:发放的|为(?=.{{0,30}}贷款授信)))"
)
_ENTERPRISE_ACCOUNT_RE = re.compile(r"(?:\d+\.)?(未结清|已结清)账户编号\s*[:：]?")

_INQUIRY_REASONS = tuple(
    sorted(
        {
            "法人代表、负责人、高管等资信审查",
            "本人查询（互联网个人信用信息服务平台）",
            "本人查询(互联网个人信用信息服务平台)",
            "本人查询（自助查询机）",
            "本人查询(自助查询机)",
            "担保资格审查",
            "信用卡审批",
            "贷款审批",
            "贷后管理",
        },
        key=len,
        reverse=True,
    )
)


def _linear(text: str) -> str:
    text = str(text or "").replace("**", "").replace("|", " ")
    return re.sub(r"\s+", " ", text).strip()


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def _iso_date(value: str) -> str:
    match = _DATE_CN_RE.search(str(value or ""))
    if match:
        return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    match = re.search(r"(20\d{2})[-./](\d{1,2})[-./](\d{1,2})", str(value or ""))
    if not match:
        return ""
    return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"


def _iso_month(value: str) -> str:
    match = re.search(r"(20\d{2})年\s*(\d{1,2})月", str(value or ""))
    if not match:
        return ""
    return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}"


def _number(value: str) -> int | float | None:
    raw = re.sub(r"[^0-9.-]", "", str(value or "").replace(",", ""))
    if not raw or raw in {"-", ".", "-."}:
        return None
    try:
        number = Decimal(raw)
    except InvalidOperation:
        return None
    return int(number) if number == number.to_integral_value() else float(number)


def _stable_id(prefix: str, *parts: Any) -> str:
    identity = "|".join(_compact(str(part or "")).upper() for part in parts)
    digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def _page_texts(parse_result: Any) -> list[tuple[int, str, str]]:
    out: list[tuple[int, str, str]] = []
    for index, page in enumerate(getattr(parse_result, "pages", []) or [], start=1):
        parts = [str(getattr(block, "content", "") or "") for block in getattr(page, "texts", []) or []]
        for kv in getattr(page, "key_values", []) or []:
            parts.extend((str(getattr(kv, "key", "") or ""), str(getattr(kv, "value", "") or "")))
        for table in getattr(page, "tables", []) or []:
            parts.extend(str(header or "") for header in getattr(table, "headers", []) or [])
            for row in getattr(table, "rows", []) or []:
                parts.extend(str(getattr(cell, "text", "") or "") for cell in getattr(row, "cells", []) or [])
        text = "\n".join(part for part in parts if part.strip())
        out.append((int(getattr(page, "page_number", 0) or index), _linear(text), _compact(text)))
    return out


def _source_page(page_texts: list[tuple[int, str, str]], fragment: str) -> int:
    needle = _compact(fragment)[:36]
    if not needle:
        return 0
    for page_number, _linear_text, compact_text in page_texts:
        if needle in compact_text:
            return page_number
    return 0


def _source_refs(page: int, method: str) -> list[dict[str, Any]]:
    ref: dict[str, Any] = {"source": method}
    if page > 0:
        ref["page"] = page
    return [ref]


def extract_native_credit_business(
    parse_result: Any,
    full_text: str,
    *,
    report_subtype: str,
    content_mode: str,
) -> dict[str, Any]:
    """Extract high-confidence native-text business records for Community output."""
    if content_mode not in {"native_text", "mixed"}:
        return {}
    if report_subtype == "personal_brief":
        return _extract_personal_brief(parse_result, full_text)
    if report_subtype == "enterprise":
        return _extract_enterprise(parse_result, full_text)
    return {}


def _extract_personal_brief(parse_result: Any, full_text: str) -> dict[str, Any]:
    text = _linear(full_text)
    page_texts = _page_texts(parse_result)
    accounts = _personal_accounts(text, page_texts)
    inquiries = _personal_inquiries(text, page_texts)
    overdue = _overdue_from_personal_accounts(accounts)
    credit_lines = _personal_credit_lines(accounts)
    return {
        "credit_accounts": accounts,
        "credit_lines": credit_lines,
        "overdue_records": overdue,
        "inquiry_records": inquiries,
        "credit_summary": {
            "source": "personal_brief_native_text",
            "account_count": len(accounts),
            "active_account_count": sum(account.get("account_status") == "active" for account in accounts),
            "settled_account_count": sum(
                account.get("account_status") in {"settled", "closed"} for account in accounts
            ),
            "overdue_account_count": len(overdue),
            "inquiry_count": len(inquiries),
            "institution_inquiry_count": sum(item.get("inquiry_type") == "institution" for item in inquiries),
            "personal_inquiry_count": sum(item.get("inquiry_type") == "personal" for item in inquiries),
        },
    }


def _personal_credit_lines(accounts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for account in accounts:
        if account.get("account_type") != "credit_line":
            continue
        account_id = str(account.get("account_id") or "")
        out.append(
            {
                "credit_line_id": _stable_id("credit_line", account_id),
                "account_id": account_id,
                "facility_type": account.get("business_type") or "贷款授信",
                "total_limit": account.get("credit_limit"),
                "used_limit": account.get("balance"),
                "currency": account.get("currency") or "CNY",
                "account_status": account.get("account_status"),
                "source": "personal_brief_narrative",
                "source_refs": list(account.get("source_refs") or []),
                "confidence": account.get("confidence", 0.9),
            }
        )
    return out


def _personal_accounts(text: str, page_texts: list[tuple[int, str, str]]) -> list[dict[str, Any]]:
    # Account narratives can continue on later pages even after a page-one
    # column has already introduced non-credit or responsibility headings.
    # The date+institution+issuance anchor is narrow enough to scan the whole
    # report without treating query dates or repayment-liability prose as an
    # account start.
    starts = list(_ACCOUNT_START_RE.finditer(text))
    accounts: list[dict[str, Any]] = []
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        chunk = text[match.start() : end].strip()
        if not any(marker in chunk for marker in ("贷记卡", "准贷记卡", "贷款", "授信")):
            continue
        if "发放的" not in chunk and not re.search(r"为.{0,30}贷款授信", chunk):
            continue
        account = _personal_account_from_chunk(chunk, page_texts)
        if not account or not account.get("account_id"):
            continue
        # Several cards can legitimately share institution, opening date,
        # currency, and even limit while the brief report masks their account
        # numbers. Preserve every numbered narrative entry and make its ordinal
        # part of the stable surrogate key instead of collapsing it.
        account["sequence"] = len(accounts) + 1
        account["account_id"] = _stable_id(
            "credit_account",
            account["account_id"],
            account["sequence"],
        )
        accounts.append(account)
    return accounts


def _personal_account_from_chunk(
    chunk: str,
    page_texts: list[tuple[int, str, str]],
) -> dict[str, Any] | None:
    opened = _DATE_CN_RE.match(chunk)
    if not opened:
        return None
    open_date = _iso_date(opened.group(0))
    remainder = chunk[opened.end() :]
    action_match = re.search(r"发放的|为(?=.{0,30}贷款授信)", remainder)
    if not action_match:
        return None
    institution = re.sub(r"\s+", "", remainder[: action_match.start()]).strip("，,。.;；")
    if len(institution) < 4 or len(institution) > 80:
        return None
    body = remainder[action_match.end() :]

    if "贷记卡" in body or "准贷记卡" in body:
        account_type = "credit_card"
        business_type = "准贷记卡" if "准贷记卡" in body else "贷记卡"
    elif "授信" in body and re.search(r"贷款授信", body):
        account_type = "credit_line"
        business_match = re.search(r"([\u3400-\u9fff（）()]{1,24}贷款)授信", body)
        business_type = business_match.group(1) if business_match else "贷款授信"
    else:
        account_type = "loan"
        business_match = re.search(r"[）)]\s*([\u3400-\u9fff（）()]{1,30}贷款)", body)
        if not business_match:
            business_match = re.search(r"([\u3400-\u9fff（）()]{1,24}贷款)", body)
        business_type = business_match.group(1) if business_match else "贷款"

    currency_match = re.search(r"[（(](人民币|美元|欧元|港币)(?:账户)?", body)
    currency_label = currency_match.group(1) if currency_match else "人民币"
    currency = {"人民币": "CNY", "美元": "USD", "欧元": "EUR", "港币": "HKD"}.get(
        currency_label,
        currency_label,
    )
    card_tail_match = re.search(r"卡片尾号\s*[:：]?\s*(\d{3,8})", body)
    card_tail = card_tail_match.group(1) if card_tail_match else ""
    page = _source_page(page_texts, chunk[:120])
    account: dict[str, Any] = {
        "account_type": account_type,
        "management_institution": institution,
        "business_type": business_type,
        "open_date": open_date,
        "currency": currency,
        "account_status": "closed" if "销户" in body else "settled" if "已结清" in body else "active",
        "source": "personal_brief_narrative",
        "source_refs": _source_refs(page, "native_text_narrative"),
        "confidence": 0.94,
    }
    if card_tail:
        account["card_tail"] = card_tail

    patterns = {
        "loan_amount": r"发放的\s*([\d,]+(?:\.\d+)?)\s*元",
        "credit_limit": r"信用额度\s*([\d,]+(?:\.\d+)?)",
        "balance": r"余额(?:为)?\s*([\d,]+(?:\.\d+)?)",
        "used_amount": r"已使用额度\s*([\d,]+(?:\.\d+)?)",
    }
    for field, pattern in patterns.items():
        amount_match = re.search(pattern, chunk)
        if amount_match:
            account[field] = _number(amount_match.group(1))

    due_match = re.search(r"(20\d{2}年\s*\d{1,2}月\s*\d{1,2}日)到期", chunk)
    if due_match:
        account["due_date"] = _iso_date(due_match.group(1))
    close_match = re.search(r"(20\d{2}年\s*\d{1,2}月)(?:已结清|销户)", chunk)
    if close_match:
        account["close_date"] = _iso_month(close_match.group(1))
    validity_match = re.search(r"额度有效期至\s*(20\d{2}年\s*\d{1,2}月\s*\d{1,2}日)", chunk)
    if validity_match and "due_date" not in account:
        account["due_date"] = _iso_date(validity_match.group(1))
    as_of_match = re.search(r"截\s*至\s*(20\d{2}年\s*\d{1,2}月(?:\s*\d{1,2}日)?)", chunk)
    if as_of_match:
        account["information_as_of"] = _iso_date(as_of_match.group(1)) or _iso_month(as_of_match.group(1))

    overdue_months = re.search(r"最近5年内有\s*(\d+)\s*个月处于逾期状态", chunk)
    if overdue_months:
        account["overdue_months_last_5y"] = int(overdue_months.group(1))
        account["ever_overdue"] = True
    elif "从未发生过逾期" in chunk or "从未逾期过" in chunk:
        account["overdue_months_last_5y"] = 0
        account["ever_overdue"] = False
    if "当前无逾期" in chunk:
        account["current_overdue"] = False
    if "没有发生过90天以上" in chunk or "没有发生过90天以上的逾期" in chunk:
        account["over_90_days"] = False
    elif "发生过90天以上" in chunk:
        account["over_90_days"] = True
    account["account_id"] = _stable_id(
        "credit_account",
        open_date,
        institution,
        business_type,
        currency,
        card_tail,
        account.get("due_date"),
        account.get("credit_limit"),
        account.get("loan_amount"),
    )
    return account


def _personal_inquiries(text: str, page_texts: list[tuple[int, str, str]]) -> list[dict[str, Any]]:
    if "机构查询记录明细" not in text:
        return []
    institution_start = text.index("机构查询记录明细")
    personal_start = text.find("个人查询记录明细", institution_start)
    institution_text = text[institution_start : personal_start if personal_start >= 0 else len(text)]
    personal_text = text[personal_start:] if personal_start >= 0 else ""
    records = [
        *_inquiry_rows(institution_text, "institution", page_texts),
        *_inquiry_rows(personal_text, "personal", page_texts),
    ]
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for record in records:
        record_id = str(record.get("inquiry_id") or "")
        if not record_id or record_id in seen:
            continue
        seen.add(record_id)
        out.append(record)
    return out


def _inquiry_rows(
    section: str,
    inquiry_type: str,
    page_texts: list[tuple[int, str, str]],
) -> list[dict[str, Any]]:
    matches = list(re.finditer(r"(?<!\d)(\d{1,4})\s+(20\d{2}年\s*\d{1,2}月\s*\d{1,2}日)\s+", section))
    out: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(section)
        rest = _compact(section[match.end() : end])
        reason = next((candidate for candidate in _INQUIRY_REASONS if candidate in rest), "")
        if not reason:
            continue
        institution = "本人" if inquiry_type == "personal" else rest.split(reason, 1)[0]
        if not institution or len(institution) > 100:
            continue
        query_date = _iso_date(match.group(2))
        page = _source_page(page_texts, f"{match.group(1)}{match.group(2)}{institution[:12]}")
        out.append(
            {
                "inquiry_id": _stable_id("credit_inquiry", inquiry_type, query_date, institution, reason),
                "sequence": int(match.group(1)),
                "inquiry_type": inquiry_type,
                "inquiry_date": query_date,
                "institution": institution,
                "reason": reason.replace("(", "（").replace(")", "）"),
                "source": "personal_brief_inquiry_ledger",
                "source_refs": _source_refs(page, "native_text_ledger"),
                "confidence": 0.97,
            }
        )
    return out


def _overdue_from_personal_accounts(accounts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for account in accounts:
        if not account.get("ever_overdue"):
            continue
        account_id = str(account.get("account_id") or "")
        out.append(
            {
                "overdue_id": _stable_id("credit_overdue", account_id, "last_5_years"),
                "account_id": account_id,
                "period_scope": "last_5_years",
                "overdue_months": int(account.get("overdue_months_last_5y") or 0),
                "over_90_days": account.get("over_90_days"),
                "current_overdue": account.get("current_overdue"),
                "source": "personal_brief_account_narrative",
                "source_refs": list(account.get("source_refs") or []),
                "confidence": account.get("confidence", 0.9),
            }
        )
    return out


def _extract_enterprise(parse_result: Any, full_text: str) -> dict[str, Any]:
    text = _linear(full_text)
    page_texts = _page_texts(parse_result)
    table_accounts = _enterprise_accounts_from_canonical_tables(parse_result)
    accounts = _merge_enterprise_accounts(table_accounts, _enterprise_accounts(text, page_texts))
    credit_lines = _enterprise_credit_lines(text, page_texts)
    public_records = _enterprise_public_records(full_text, page_texts)
    summary = _enterprise_summary(text, parse_result=parse_result)
    summary.update(
        {
            "source": "enterprise_native_text",
            "extracted_account_count": len(accounts),
            "canonical_table_account_count": len(table_accounts),
            "credit_line_count": len(credit_lines),
            "public_record_count": len(public_records),
        }
    )
    return {
        "credit_accounts": accounts,
        "credit_lines": credit_lines,
        "overdue_records": _overdue_from_enterprise_accounts(accounts),
        "inquiry_records": [],
        "public_records": public_records,
        "credit_summary": summary,
    }


def _enterprise_accounts_from_canonical_tables(parse_result: Any) -> list[dict[str, Any]]:
    """Extract enterprise account identity/detail fields from physical tables.

    This is intentionally a domain mapper, not a table reconstructor.  It only
    consumes the canonical ``raw_rows`` and cell provenance already produced by
    the generic PDF pipeline.
    """
    schemas_by_width: dict[int, dict[str, int]] = {}
    records: dict[str, dict[str, Any]] = {}
    for page in getattr(parse_result, "pages", []) or []:
        page_number = int(getattr(page, "page_number", 0) or 0)
        for table in getattr(page, "tables", []) or []:
            metadata = dict(getattr(table, "metadata", None) or {})
            raw_rows = metadata.get("raw_rows") if isinstance(metadata.get("raw_rows"), list) else []
            rows = [[_compact(str(value or "")) for value in row] for row in raw_rows if isinstance(row, list)]
            if not rows:
                continue
            width = max((len(row) for row in rows), default=0)
            for row_index, row in enumerate(rows):
                schema = _enterprise_account_table_schema(row)
                if schema:
                    schemas_by_width[width] = schema
                    continue
                schema = schemas_by_width.get(width)
                if not schema:
                    continue
                account_col = schema.get("account_identifier", 0)
                raw_identifier = row[account_col] if account_col < len(row) else ""
                account_identifier = re.sub(r"[^A-Z0-9]", "", raw_identifier.upper())
                if len(account_identifier) < 12 or not re.search(r"[A-Z]", account_identifier):
                    continue
                values = {field: row[col] if col < len(row) else "" for field, col in schema.items()}
                record = records.setdefault(
                    account_identifier,
                    {
                        "account_id": f"credit_account:{account_identifier}",
                        "account_identifier": account_identifier,
                        "account_type": "enterprise_credit",
                        "account_status": "active",
                        "source": "canonical_physical_table",
                        "source_refs": [],
                        "confidence": 1.0,
                    },
                )
                source_ref = {
                    "source": "canonical_physical_table",
                    "page": page_number,
                    "table_id": str(getattr(table, "table_id", "") or ""),
                    "row": row_index,
                }
                if source_ref not in record["source_refs"]:
                    record["source_refs"].append(source_ref)
                _set_if_value(record, "management_institution", values.get("management_institution"))
                _set_if_value(record, "business_type", values.get("business_type"))
                open_date = _iso_date(values.get("open_date", ""))
                due_date = _iso_date(values.get("due_date", ""))
                close_date = _iso_date(values.get("close_date", ""))
                if open_date:
                    record["open_date"] = open_date
                if due_date:
                    record["due_date"] = due_date
                if close_date:
                    record["close_date"] = close_date
                    record["account_status"] = "settled"
                currency = _currency_code(values.get("currency", ""))
                if currency:
                    record["currency"] = currency
                amount = _number(values.get("loan_amount", ""))
                if amount is not None:
                    record["loan_amount"] = amount
    return list(records.values())


def _enterprise_account_table_schema(row: list[str]) -> dict[str, int]:
    aliases = {
        "account_identifier": ("账户编号", "账户号"),
        "management_institution": ("授信机构",),
        "business_type": ("业务种类", "业务类型"),
        "open_date": ("开立日期", "开户日期"),
        "due_date": ("到期日", "到期日期"),
        "close_date": ("关闭日期", "结清日期"),
        "currency": ("币种",),
        "loan_amount": ("借款金额", "贴现金额", "授信金额"),
    }
    schema: dict[str, int] = {}
    for col_index, label in enumerate(row):
        for field, candidates in aliases.items():
            if any(candidate in label for candidate in candidates):
                schema.setdefault(field, col_index)
    required = {"account_identifier", "open_date", "due_date", "currency", "loan_amount"}
    return schema if required.issubset(schema) else {}


def _merge_enterprise_accounts(
    canonical: list[dict[str, Any]],
    narrative: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    narrative_identifiers = {
        str(item.get("account_identifier") or "") for item in narrative if item.get("account_identifier")
    }
    by_identifier: dict[str, dict[str, Any]] = {
        identifier: dict(item)
        for item in canonical
        if (identifier := str(item.get("account_identifier") or ""))
        and not (
            identifier not in narrative_identifiers
            and any(candidate.startswith(identifier) for candidate in narrative_identifiers)
        )
    }
    for item in narrative:
        identifier = str(item.get("account_identifier") or "")
        if not identifier or identifier not in by_identifier:
            if identifier:
                by_identifier[identifier] = dict(item)
            continue
        target = by_identifier[identifier]
        for key, value in item.items():
            if key == "source_refs":
                refs = list(target.get("source_refs") or [])
                for ref in value or []:
                    if ref not in refs:
                        refs.append(ref)
                target["source_refs"] = refs
            elif key in {"source", "confidence"}:
                continue
            elif value not in (None, "", [], {}) and target.get(key) in (None, "", [], {}):
                target[key] = value
            elif key == "account_status" and value:
                target[key] = value
    return list(by_identifier.values())


def _set_if_value(target: dict[str, Any], key: str, value: Any) -> None:
    compact = re.sub(r"\s+", "", str(value or ""))
    if compact and compact != "--":
        target[key] = compact


def _currency_code(value: str) -> str:
    compact = _compact(value)
    for label, code in (("人民币", "CNY"), ("美元", "USD"), ("欧元", "EUR"), ("港币", "HKD")):
        if label in compact:
            return code
    return compact if compact and compact != "--" else ""


def _enterprise_summary(text: str, *, parse_result: Any | None = None) -> dict[str, Any]:
    summary = _enterprise_summary_from_canonical_tables(parse_result)
    first_trade = re.search(
        r"首次有信贷交易的年份\s+发生信贷交易的机构数\s+当前有未结清信贷\s*交易的机构数\s+"
        r"首次有相关还款\s*责任的年份\s+(20\d{2})\s+(\d{1,3})\s+(\d{1,3})\s+(20\d{2})",
        text[:30_000],
    )
    if first_trade:
        for key, value in {
            "first_credit_year": int(first_trade.group(1)),
            "credit_institution_count": int(first_trade.group(2)),
            "active_credit_institution_count": int(first_trade.group(3)),
            "first_repayment_responsibility_year": int(first_trade.group(4)),
        }.items():
            summary.setdefault(key, value)
    balances = re.search(
        r"借贷交易担保交易余额([\d.]+)余额([\d.]+)其中[:：]?被追偿余额([\d.]+)",
        _compact(text[:30_000]),
    )
    if balances:
        summary.update(
            {
                "credit_balance": _number(balances.group(1)),
                "guarantee_balance": _number(balances.group(2)),
                "recovered_debt_balance": _number(balances.group(3)),
                "amount_unit": "CNY_10K",
            }
        )
    public_counts = re.search(
        r"非信贷交易账户数\s+欠税记录条数\s+民事判决记录条数\s+强制执行记录条数\s+行政处罚记录条数"
        r"\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)",
        text,
    )
    if public_counts:
        summary["public_record_counts"] = {
            "non_credit_accounts": int(public_counts.group(1)),
            "tax_arrears": int(public_counts.group(2)),
            "civil_judgments": int(public_counts.group(3)),
            "enforcements": int(public_counts.group(4)),
            "administrative_penalties": int(public_counts.group(5)),
        }
    return summary


def _enterprise_summary_from_canonical_tables(parse_result: Any | None) -> dict[str, Any]:
    """Read the enterprise overview row from canonical physical tables."""
    summary: dict[str, Any] = {}
    aliases = {
        "first_credit_year": "首次有信贷交易的年份",
        "credit_institution_count": "发生信贷交易的机构数",
        "active_credit_institution_count": "当前有未结清信贷交易的机构数",
        "first_repayment_responsibility_year": "首次有相关还款责任的年份",
    }
    for page in getattr(parse_result, "pages", []) or []:
        for table in getattr(page, "tables", []) or []:
            metadata = dict(getattr(table, "metadata", None) or {})
            raw_rows = metadata.get("raw_rows") if isinstance(metadata.get("raw_rows"), list) else []
            compact_rows = [[_compact(value) for value in row] for row in raw_rows if isinstance(row, list)]
            for row_index, row in enumerate(compact_rows[:-1]):
                if not (any("借贷交易" in value for value in row) and any("担保交易" in value for value in row)):
                    continue
                balance_row = compact_rows[row_index + 1]
                if len(balance_row) >= 4 and balance_row[0] == "余额" and balance_row[2] == "余额":
                    credit_balance = _number(balance_row[1])
                    guarantee_balance = _number(balance_row[3])
                    if credit_balance is not None and guarantee_balance is not None:
                        summary.update(
                            {
                                "credit_balance": credit_balance,
                                "guarantee_balance": guarantee_balance,
                                "amount_unit": "CNY_10K",
                            }
                        )
                if row_index + 2 < len(compact_rows):
                    recovery_row = compact_rows[row_index + 2]
                    recovered = next(
                        (
                            _number(recovery_row[index + 1])
                            for index, value in enumerate(recovery_row[:-1])
                            if "被追偿余额" in value
                        ),
                        None,
                    )
                    if recovered is not None:
                        summary["recovered_debt_balance"] = recovered

            headers = [_compact(value) for value in (getattr(table, "headers", None) or [])]
            columns = {
                field: next((index for index, header in enumerate(headers) if label in header), -1)
                for field, label in aliases.items()
            }
            if any(index < 0 for index in columns.values()):
                continue
            for row in getattr(table, "rows", []) or []:
                values = [_compact(getattr(cell, "text", cell)) for cell in (getattr(row, "cells", []) or [])]
                projected: dict[str, int] = {}
                for field, column in columns.items():
                    value = values[column] if column < len(values) else ""
                    if not value.isdigit():
                        projected = {}
                        break
                    projected[field] = int(value)
                if (
                    projected
                    and 1900 <= projected["first_credit_year"] <= 2100
                    and 1900 <= projected["first_repayment_responsibility_year"] <= 2100
                ):
                    summary.update(projected)
                    break
    return summary


def _enterprise_accounts(text: str, page_texts: list[tuple[int, str, str]]) -> list[dict[str, Any]]:
    starts = list(_ENTERPRISE_ACCOUNT_RE.finditer(text))
    accounts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        chunk = text[match.start() : min(end, match.start() + 8_000)]
        account_id_match = re.search(r"账户编号\s*[:：]?\s*([A-Z0-9\s]+?)(?=\s*授信机构\s*[:：])", chunk)
        institution_match = re.search(r"授信机构\s*[:：]\s*(.+?)\s*业务种类\s*[:：]", chunk)
        business_match = re.search(
            r"业务种类\s*[:：]\s*(.+?)(?=\s*(?:信息报告日期|信贷明细|开户日期|授信机构|第\s*\d+\s*页))",
            chunk,
        )
        if not account_id_match or not institution_match or not business_match:
            continue
        account_identifier = re.sub(r"[^A-Z0-9]", "", account_id_match.group(1).upper())
        institution = re.sub(r"\s+", "", institution_match.group(1))
        business_type = re.sub(r"\s+", "", business_match.group(1)).strip("，,。.;；")
        if len(account_identifier) < 12 or not institution or len(business_type) > 50:
            continue
        account_id = f"credit_account:{account_identifier}"
        if account_id in seen:
            continue
        seen.add(account_id)
        page = _source_page(page_texts, account_identifier[:24])
        account: dict[str, Any] = {
            "account_id": account_id,
            "account_identifier": account_identifier,
            "account_type": "enterprise_credit",
            "management_institution": institution,
            "business_type": business_type,
            "account_status": "active" if match.group(1) == "未结清" else "settled",
            "source": "enterprise_account_history",
            "source_refs": _source_refs(page, "native_text_account_card"),
            "confidence": 0.96,
        }
        five_tier = re.search(r"(?:五级分类.{0,120}?)(正常|关注|次级|可疑|损失|违约|未分类)", chunk)
        if five_tier:
            account["five_tier_class"] = five_tier.group(1)
        detail = re.search(
            r"开户日期\s+到期日\s+币种\s+(?:贴现金额|借款金额).{0,160}?"
            r"(20\d{2}-\d{1,2}-\d{1,2})\s+(20\d{2}-\d{1,2}-\d{1,2})\s+"
            r"(人民币元|美元|欧元|港币)\s+([\d,.]+)",
            chunk,
        )
        if detail:
            account.update(
                {
                    "open_date": _iso_date(detail.group(1)),
                    "due_date": _iso_date(detail.group(2)),
                    "currency": {"人民币元": "CNY", "美元": "USD", "欧元": "EUR", "港币": "HKD"}.get(
                        detail.group(3),
                        detail.group(3),
                    ),
                    "loan_amount": _number(detail.group(4)),
                }
            )
        accounts.append(account)
    return accounts


def _enterprise_credit_lines(text: str, page_texts: list[tuple[int, str, str]]) -> list[dict[str, Any]]:
    marker = re.search(r"非循环信用额度\s+循环信用额度", text)
    if not marker:
        return []
    tail = text[marker.start() : marker.start() + 800]
    responsibility = tail.find("责任类型")
    if responsibility >= 0:
        tail = tail[:responsibility]
    values = re.findall(r"(?<![\d.-])\d+(?:\.\d+)?(?![\d.-])", tail)
    # Page footer contributes page/total numbers; the six facility values are
    # the final six numbers before the following responsibility section.
    if len(values) < 6:
        return []
    totals = [_number(value) for value in values[-6:]]
    page = _source_page(page_texts, "非循环信用额度循环信用额度")
    labels = ("non_revolving", "revolving")
    out: list[dict[str, Any]] = []
    for index, label in enumerate(labels):
        offset = index * 3
        out.append(
            {
                "credit_line_id": _stable_id("credit_line", label, *totals[offset : offset + 3]),
                "facility_type": label,
                "total_limit": totals[offset],
                "used_limit": totals[offset + 1],
                "available_limit": totals[offset + 2],
                "currency": "CNY",
                "amount_unit": "CNY_10K",
                "source": "enterprise_credit_summary",
                "source_refs": _source_refs(page, "native_text_summary_table"),
                "confidence": 0.92,
            }
        )
    return out


def _enterprise_public_records(
    raw_text: str,
    page_texts: list[tuple[int, str, str]],
) -> list[dict[str, Any]]:
    if "公共记录明细" not in raw_text:
        return []
    section = raw_text[raw_text.index("公共记录明细") :]
    end = section.find("附件1")
    if end >= 0:
        section = section[:end]
    lines = [_linear(line) for line in section.splitlines() if _linear(line)]
    license_header = next((index for index, line in enumerate(lines) if line.startswith("许可部门")), -1)
    certification_header = next((index for index, line in enumerate(lines) if line.startswith("认证部门")), -1)
    out: list[dict[str, Any]] = []
    if license_header >= 0:
        stop = certification_header if certification_header > license_header else len(lines)
        license_lines = lines[license_header + 1 : stop]
        license_records = _public_license_rows(license_lines, page_texts)
        out.extend(license_records or _public_license_column_rows(license_lines, page_texts))
    if certification_header >= 0:
        certification_lines = lines[certification_header + 1 :]
        certification_records = _public_certification_rows(certification_lines, page_texts)
        out.extend(certification_records or _public_certification_column_rows(certification_lines, page_texts))
    for sequence, record in enumerate(out, start=1):
        record["sequence"] = sequence
        record["public_record_id"] = _stable_id(
            "public_record",
            record.get("record_type"),
            record.get("authority"),
            record.get("category"),
            record.get("start_date"),
            record.get("end_date"),
            record.get("content"),
            sequence,
        )
    return out


_LICENSE_ROW_RE = re.compile(
    r"^(.*?)\s+(普通|特殊|一般)\s+(20\d{2}-\d{2}-\d{2})\s+"
    r"(20\d{2}-\d{2}-\d{2})\s+(.+)$"
)
_CERTIFICATION_ROW_RE = re.compile(
    r"^(.*?)\s+([^\s]{2,40})\s+(--|20\d{2}-\d{2}-\d{2})\s+"
    r"(--|20\d{2}-\d{2}-\d{2})\s+(.+)$"
)


def _looks_like_authority_prefix(line: str) -> bool:
    compact = _compact(line)
    if not compact or len(compact) > 40 or re.search(r"\d|许可部门|认证部门|受篇幅|第.*页", compact):
        return False
    return compact.startswith(("国家", "中国")) or any(marker in compact for marker in ("省", "市", "区", "县"))


def _public_row_noise(line: str) -> bool:
    compact = _compact(line)
    return not compact or bool(
        re.fullmatch(r"第?\d+页(?:/共)?", compact)
        or re.fullmatch(r"\d+页", compact)
        or compact in {"第", "页"}
        or re.fullmatch(r"页/共\d*", compact)
        or compact.startswith(("受篇幅所限", "许可部门", "认证部门", "附件"))
    )


def _table_row_matches(
    lines: list[str],
    pattern: re.Pattern[str],
) -> list[tuple[int, int, re.Match[str], str]]:
    rows: list[tuple[int, int, re.Match[str], str]] = []
    for line_index, line in enumerate(lines):
        match = pattern.match(line)
        if not match:
            continue
        authority = match.group(1)
        start_index = line_index
        if line_index > 0 and _looks_like_authority_prefix(lines[line_index - 1]):
            authority = f"{lines[line_index - 1]}{authority}"
            start_index = line_index - 1
        rows.append((start_index, line_index, match, authority))
    return rows


def _public_license_rows(
    lines: list[str],
    page_texts: list[tuple[int, str, str]],
) -> list[dict[str, Any]]:
    rows = _table_row_matches(lines, _LICENSE_ROW_RE)
    out: list[dict[str, Any]] = []
    for index, (_start, line_index, match, authority_raw) in enumerate(rows):
        next_start = rows[index + 1][0] if index + 1 < len(rows) else len(lines)
        continuation = "".join(line for line in lines[line_index + 1 : next_start] if not _public_row_noise(line))
        authority = _compact(authority_raw)
        content = _compact(f"{match.group(5)}{continuation}").strip("，,。.;；")
        if not authority or len(authority) > 60 or not content:
            continue
        page = _source_page(page_texts, f"{authority}{match.group(3)}")
        out.append(
            {
                "record_type": "license",
                "authority": authority,
                "category": match.group(2),
                "start_date": match.group(3),
                "end_date": match.group(4),
                "content": content,
                "source": "enterprise_public_record_table",
                "source_refs": _source_refs(page, "native_text_table"),
                "confidence": 0.96,
            }
        )
    return out


def _public_certification_rows(
    lines: list[str],
    page_texts: list[tuple[int, str, str]],
) -> list[dict[str, Any]]:
    rows = _table_row_matches(lines, _CERTIFICATION_ROW_RE)
    out: list[dict[str, Any]] = []
    for index, (_start, line_index, match, authority_raw) in enumerate(rows):
        next_start = rows[index + 1][0] if index + 1 < len(rows) else len(lines)
        continuation = "".join(line for line in lines[line_index + 1 : next_start] if not _public_row_noise(line))
        authority = _compact(authority_raw)
        content = _compact(f"{match.group(5)}{continuation}").strip("，,。.;；")
        if not authority or len(authority) > 60 or not content:
            continue
        page = _source_page(page_texts, f"{authority}{match.group(4)}")
        out.append(
            {
                "record_type": "certification",
                "authority": authority,
                "category": match.group(2),
                "start_date": "" if match.group(3) == "--" else match.group(3),
                "end_date": "" if match.group(4) == "--" else match.group(4),
                "content": content,
                "source": "enterprise_public_record_table",
                "source_refs": _source_refs(page, "native_text_table"),
                "confidence": 0.95,
            }
        )
    return out


def _columnar_authority_start(lines: list[str], category_index: int, floor: int) -> int:
    start = category_index - 1
    while start > floor and _looks_like_authority_prefix(lines[start - 1]):
        start -= 1
    return start


def _columnar_public_anchors(
    lines: list[str],
    *,
    category_ok: Any,
    header_tail: str,
) -> list[tuple[int, int]]:
    floor = next((index + 1 for index, line in enumerate(lines) if _compact(line) == header_tail), 0)
    anchors: list[tuple[int, int]] = []
    for index in range(floor + 1, len(lines) - 2):
        if not category_ok(lines[index]):
            continue
        if not re.fullmatch(r"--|20\d{2}-\d{2}-\d{2}", _compact(lines[index + 1])):
            continue
        if not re.fullmatch(r"--|20\d{2}-\d{2}-\d{2}", _compact(lines[index + 2])):
            continue
        authority_start = _columnar_authority_start(lines, index, floor)
        if authority_start < floor or authority_start >= index:
            continue
        anchors.append((authority_start, index))
    return anchors


def _columnar_content(lines: list[str], start: int, end: int) -> str:
    parts: list[str] = []
    for line in lines[start:end]:
        if _public_row_noise(line):
            continue
        compact = _compact(line)
        if compact.startswith(("一、", "二、", "三、")):
            break
        parts.append(line)
    return _compact("".join(parts)).strip("，,。.;；")


def _public_license_column_rows(
    lines: list[str],
    page_texts: list[tuple[int, str, str]],
) -> list[dict[str, Any]]:
    anchors = _columnar_public_anchors(
        lines,
        category_ok=lambda value: _compact(value) in {"普通", "特殊", "一般"},
        header_tail="许可内容",
    )
    out: list[dict[str, Any]] = []
    for index, (authority_start, category_index) in enumerate(anchors):
        next_start = anchors[index + 1][0] if index + 1 < len(anchors) else len(lines)
        authority = _compact("".join(lines[authority_start:category_index]))
        content = _columnar_content(lines, category_index + 3, next_start)
        if not authority or len(authority) > 60 or not content:
            continue
        start_date = _compact(lines[category_index + 1])
        end_date = _compact(lines[category_index + 2])
        page = _source_page(page_texts, f"{authority}{start_date}")
        out.append(
            {
                "record_type": "license",
                "authority": authority,
                "category": _compact(lines[category_index]),
                "start_date": start_date,
                "end_date": end_date,
                "content": content,
                "source": "enterprise_public_record_table",
                "source_refs": _source_refs(page, "native_text_columnar_table"),
                "confidence": 0.94,
            }
        )
    return out


def _public_certification_column_rows(
    lines: list[str],
    page_texts: list[tuple[int, str, str]],
) -> list[dict[str, Any]]:
    header_tokens = {"认证类型", "认证日期", "截止日期", "认证内容"}
    anchors = _columnar_public_anchors(
        lines,
        category_ok=lambda value: (
            bool(_compact(value)) and _compact(value) not in header_tokens and len(_compact(value)) <= 40
        ),
        header_tail="认证内容",
    )
    out: list[dict[str, Any]] = []
    for index, (authority_start, category_index) in enumerate(anchors):
        next_start = anchors[index + 1][0] if index + 1 < len(anchors) else len(lines)
        authority = _compact("".join(lines[authority_start:category_index]))
        content = _columnar_content(lines, category_index + 3, next_start)
        if not authority or len(authority) > 60 or not content:
            continue
        start_date = _compact(lines[category_index + 1])
        end_date = _compact(lines[category_index + 2])
        page = _source_page(page_texts, f"{authority}{end_date}")
        out.append(
            {
                "record_type": "certification",
                "authority": authority,
                "category": _compact(lines[category_index]),
                "start_date": "" if start_date == "--" else start_date,
                "end_date": "" if end_date == "--" else end_date,
                "content": content,
                "source": "enterprise_public_record_table",
                "source_refs": _source_refs(page, "native_text_columnar_table"),
                "confidence": 0.93,
            }
        )
    return out


def _overdue_from_enterprise_accounts(accounts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return derive_overdue_records(accounts, [])


def _plain(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    for key in ("normalized_value", "normalized", "value", "raw_value", "raw"):
        if value.get(key) not in (None, ""):
            return value[key]
    return None


def derive_overdue_records(
    credit_accounts: list[Any],
    repayment_records: list[Any],
    existing: list[Any] | None = None,
) -> list[dict[str, Any]]:
    """Build one canonical overdue view from narrative, account, and month-grid facts."""
    out = [dict(item) for item in existing or [] if isinstance(item, dict)]
    seen = {str(item.get("overdue_id") or "") for item in out}
    for account in credit_accounts or []:
        if not isinstance(account, dict):
            continue
        status = str(_plain(account.get("account_status")) or "")
        five_tier = str(_plain(account.get("five_tier_class")) or "")
        overdue_amount = _number(str(_plain(account.get("overdue_amount")) or ""))
        if status not in {"逾期", "overdue"} and five_tier not in {"关注", "次级", "可疑", "损失", "违约"}:
            if not overdue_amount:
                continue
        account_id = str(account.get("account_id") or account.get("source_structure_id") or "")
        overdue_id = _stable_id("credit_overdue", account_id, "account_snapshot")
        if overdue_id in seen:
            continue
        seen.add(overdue_id)
        out.append(
            {
                "overdue_id": overdue_id,
                "account_id": account_id,
                "period_scope": "account_snapshot",
                "overdue_amount": overdue_amount,
                "five_tier_class": five_tier,
                "source": "credit_account_snapshot",
                "source_refs": list(account.get("source_refs") or []),
                "confidence": account.get("confidence", 0.8),
            }
        )
    for record in repayment_records or []:
        if not isinstance(record, dict):
            continue
        status = str(record.get("status") or "")
        if status not in {"1", "2", "3", "4", "5", "6", "7"}:
            continue
        account_id = str(record.get("account_id") or record.get("grid_id") or "")
        try:
            year = int(record.get("year") or 0)
            month = int(record.get("month") or 0)
        except (TypeError, ValueError):
            continue
        overdue_id = _stable_id("credit_overdue", account_id, year, month)
        if overdue_id in seen:
            continue
        seen.add(overdue_id)
        out.append(
            {
                "overdue_id": overdue_id,
                "account_id": account_id,
                "period_scope": "month",
                "year": year,
                "month": month,
                "overdue_level": int(status),
                "overdue_amount": _number(str(record.get("overdue_amount") or "")),
                "source": "repayment_micro_grid",
                "source_cell_refs": list(record.get("source_cell_refs") or []),
                "confidence": record.get("confidence", 0.8),
            }
        )
    return out


__all__ = ["derive_overdue_records", "extract_native_credit_business"]
