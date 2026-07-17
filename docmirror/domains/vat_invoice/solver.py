# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""VAT invoice semantic solver.

The P0 solver targets OCR text from Chinese VAT invoices.  It extracts core
invoice fields, line item amounts, and validates the amount equation without
claiming template-perfect coverage.
"""

from __future__ import annotations

import re
from typing import Any

from docmirror.domains.base import DomainSolution

_MONEY_RE = re.compile(r"[¥￥]?\s*(\d{1,3}(?:,\d{3})*|\d+)\.(\d{2})")
_INVOICE_CODE_RE = re.compile(r"发票代码[:：]?\s*(?P<value>\d{10,12})")
_INVOICE_NUMBER_RE = re.compile(r"发票号码[:：]?\s*(?P<value>\d{6,12})")
_CHECK_CODE_RE = re.compile(r"校验码[:：]?\s*(?P<value>\d{10,30})")
_MACHINE_NUMBER_RE = re.compile(r"机器编号[:：]?\s*(?P<value>\d{8,20})")
_ISSUE_DATE_RE = re.compile(r"开票日期[:：]?\s*(?P<y>20\d{2})年(?P<m>\d{1,2})月(?P<d>\d{1,2})日")
_TAX_ID_RE = re.compile(r"纳税人识别号[:：]?\s*(?P<value>[0-9A-Z]{12,25})")
_BANK_ACCOUNT_RE = re.compile(r"开户行及账号[:：]?\s*(?P<value>[^\n\r]+)")
_ADDRESS_PHONE_RE = re.compile(r"地址、电话[:：]?\s*(?P<value>[^\n\r]+)")
_ITEM_RE = re.compile(r"\*[^*\s\n\r]+\*[^\s\n\r]+")


class VATInvoiceSemanticSolver:
    """Solve core VAT invoice fields from OCR text."""

    domain = "vat_invoice"

    def solve(self, *, full_text: str, parse_result: Any = None) -> DomainSolution:
        text = _normalize_text(full_text or getattr(parse_result, "full_text", "") or "")
        english_vat = bool(
            re.search(r"Value\s*-?\s*Added\s+Tax\s+Invoice", text, re.IGNORECASE)
            and re.search(r"Invoice\s+(?:Code|Number)", text, re.IGNORECASE)
        )
        if not english_vat and ("发票" not in text or "纳税人识别号" not in text):
            return DomainSolution(
                domain=self.domain,
                status="failed",
                diagnostics=({"reason": "missing_vat_invoice_markers"},),
            )

        fields = _extract_english_fields(text) if english_vat else _extract_fields(text)
        line_items = _extract_english_line_items(text) if english_vat else _extract_line_items(text)
        invariants = _evaluate_invariants(fields, line_items)
        required_failures = [item for item in invariants if item["status"] == "fail" and item.get("required")]
        field_coverage = _field_coverage(fields)
        if required_failures:
            status = "degraded"
        elif field_coverage >= 0.7:
            status = "success"
        else:
            status = "needs_review"

        canonical = {
            "fields": fields,
            "line_items": line_items,
            "summary": _summary(fields, line_items),
        }
        return DomainSolution(
            domain=self.domain,
            canonical_model=canonical,
            invariant_results=tuple(invariants),
            confidence=round(field_coverage, 4),
            status=status,
            diagnostics=(
                {
                    "field_coverage": round(field_coverage, 4),
                    "line_item_count": len(line_items),
                    "source": "vat_invoice_text_solver_p0",
                },
            ),
        )


def _normalize_text(text: str) -> str:
    return (
        str(text or "")
        .replace("：", ":")
        .replace("（", "(")
        .replace("）", ")")
        .replace("圆", "元")
        .replace("税霸", "税额")
        .replace("精售方", "销售方")
        .replace("复票专用单", "发票专用章")
    )


def _extract_fields(text: str) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    _put_match(fields, "invoice_code", _INVOICE_CODE_RE.search(text))
    _put_match(fields, "invoice_number", _INVOICE_NUMBER_RE.search(text))
    _put_match(fields, "check_code", _CHECK_CODE_RE.search(text))
    _put_match(fields, "machine_number", _MACHINE_NUMBER_RE.search(text))
    if m := _ISSUE_DATE_RE.search(text):
        fields["issue_date"] = f"{int(m.group('y')):04d}-{int(m.group('m')):02d}-{int(m.group('d')):02d}"

    tax_ids = [m.group("value") for m in _TAX_ID_RE.finditer(text)]
    if tax_ids:
        fields["buyer_tax_id"] = tax_ids[0]
    if len(tax_ids) > 1:
        fields["seller_tax_id"] = tax_ids[1]

    names = _extract_party_names(text)
    fields.update(names)

    addresses = [m.group("value").strip() for m in _ADDRESS_PHONE_RE.finditer(text)]
    if addresses:
        fields["buyer_address_phone"] = _clean_address_phone(addresses[0])
    if len(addresses) > 1:
        fields["seller_address_phone"] = _clean_address_phone(addresses[1])

    bank_accounts = [m.group("value").strip() for m in _BANK_ACCOUNT_RE.finditer(text)]
    if bank_accounts:
        fields["buyer_bank_account"] = _clean_bank_account(bank_accounts[0])
    if len(bank_accounts) > 1:
        fields["seller_bank_account"] = _clean_bank_account(bank_accounts[1])

    moneys = _money_values(text)
    total = _money_after(text, "小写") if "价税合计" in text else None
    if total is None and moneys:
        total = moneys[-1]
    if total is not None:
        fields["total_amount"] = _fmt_money(total)
        if pair := _amount_tax_pair(moneys, total):
            amount, tax = pair
            fields["amount_without_tax"] = _fmt_money(amount)
            fields["tax_amount"] = _fmt_money(tax)

    if total_upper := _line_after_marker(text, "价税合计"):
        if "元" in total_upper or "整" in total_upper:
            fields["total_amount_in_words"] = total_upper
    if issuer := _inline_label_value(text, "开票人"):
        fields["issuer"] = issuer
    if reviewer := _inline_label_value(text, "复核"):
        fields["reviewer"] = reviewer
    if payee := _inline_label_value(text, "收款人"):
        fields["payee"] = payee
    return fields


def _flat_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _english_value(text: str, label: str, stop_labels: tuple[str, ...]) -> str:
    stop = "|".join(re.escape(item) for item in stop_labels)
    match = re.search(
        rf"(?:^|\s){re.escape(label)}\s*:\s*(.+?)(?=\s+(?:{stop})\s*:|$)",
        text,
        re.IGNORECASE,
    )
    return match.group(1).strip() if match else ""


def _english_money(text: str, label_pattern: str) -> str:
    match = re.search(
        rf"{label_pattern}\s*:\s*(?:CNY|¥|￥)?\s*([\d,]+\.\d{{2}})",
        text,
        re.IGNORECASE,
    )
    return match.group(1).replace(",", "") if match else ""


def _extract_english_fields(text: str) -> dict[str, Any]:
    flat = _flat_text(text)
    fields: dict[str, Any] = {}
    scalar_patterns = {
        "invoice_code": r"Invoice\s+Code\s*:\s*(\d{10,12})",
        "invoice_number": r"Invoice\s+Number\s*:\s*(\d{6,12})",
        "invoice_date": r"Issue\s+Date\s*:\s*(20\d{2}-\d{2}-\d{2})",
        "seller_tax_id": r"Seller\s+Tax\s+ID\s*:\s*([0-9A-Z]{12,25})",
        "buyer_tax_id": r"Buyer\s+Tax\s+ID\s*:\s*([0-9A-Z]{12,25})",
        "tax_rate": r"VAT\s+Rate\s*:\s*(\d+(?:\.\d+)?%)",
    }
    for key, pattern in scalar_patterns.items():
        match = re.search(pattern, flat, re.IGNORECASE)
        if match:
            fields[key] = match.group(1)
    if fields.get("invoice_date"):
        fields["issue_date"] = fields["invoice_date"]

    party_stops = (
        "Seller Tax ID",
        "Buyer",
        "Buyer Tax ID",
        "Total Amount",
        "VAT Rate",
        "VAT Amount",
        "Item Description",
    )
    seller = _english_value(flat, "Seller", party_stops)
    buyer = _english_value(flat, "Buyer", party_stops)
    if seller:
        fields["seller_name"] = seller
    if buyer:
        fields["buyer_name"] = buyer

    amount_without_tax = _english_money(flat, r"Total\s+Amount\s*\(excl\.\s*tax\)")
    tax_amount = _english_money(flat, r"VAT\s+Amount")
    total_amount = _english_money(flat, r"Total\s+Amount\s*\(incl\.\s*tax\)")
    if amount_without_tax:
        fields["amount_without_tax"] = amount_without_tax
    if tax_amount:
        fields["tax_amount"] = tax_amount
    if total_amount:
        fields["total_amount"] = total_amount

    person_stops = (
        "Payee",
        "Reviewer",
        "Drawer",
        "Value-Added Tax Invoice",
        "Special VAT Invoice",
        "Total Amount",
        "Item Description",
    )
    for key, label in (("payee", "Payee"), ("reviewer", "Reviewer"), ("issuer", "Drawer")):
        value = _english_value(flat, label, person_stops)
        if value:
            fields[key] = value
    return fields


def _extract_english_line_items(text: str) -> list[dict[str, Any]]:
    flat = _flat_text(text)
    match = re.search(
        r"Item\s+Description\s+Qty\s+Unit\s+Price\s+Amount\s+(.+?)(?=\s+Payee\s*:|$)",
        flat,
        re.IGNORECASE,
    )
    if not match:
        return []
    segment = match.group(1).strip()
    money = r"[\d,]+\.\d{2}"
    pattern = re.compile(
        rf"(?P<line_no>\d+)\s+(?P<description>.+?)\s+(?P<quantity>\d+(?:\.\d+)?)\s+"
        rf"(?P<unit_price>{money})\s+(?P<amount>{money})(?=\s+\d+\s+|$)"
    )
    line_items: list[dict[str, Any]] = []
    for item in pattern.finditer(segment):
        line_items.append(
            {
                "line_no": int(item.group("line_no")),
                "description": item.group("description").strip(),
                "quantity": float(item.group("quantity")),
                "unit_price": float(item.group("unit_price").replace(",", "")),
                "amount": float(item.group("amount").replace(",", "")),
                "currency": "CNY",
            }
        )
    return line_items


def _extract_party_names(text: str) -> dict[str, str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    out: dict[str, str] = {}
    for idx, line in enumerate(lines):
        if "称:" in line or "名称:" in line or line == "称":
            value = (
                line.split("称:", 1)[1].strip()
                if "称:" in line
                else line.split(":", 1)[1].strip()
                if ":" in line
                else ""
            )
            if not value and idx + 1 < len(lines):
                value = lines[idx + 1].strip()
            value = _clean_company_name(value)
            if value and "有限公司" in value:
                if "buyer_name" not in out:
                    out["buyer_name"] = value
                elif "seller_name" not in out:
                    out["seller_name"] = value
    if "seller_name" not in out:
        companies = [line for line in lines if "有限公司" in line]
        if companies:
            out.setdefault("buyer_name", companies[0])
        if len(companies) > 1:
            out["seller_name"] = companies[-1]
    return out


def _extract_line_items(text: str) -> list[dict[str, Any]]:
    item_match = _ITEM_RE.search(text)
    if not item_match:
        return []
    item_name = item_match.group(0).strip()
    fields = _extract_fields(text)
    item: dict[str, Any] = {
        "item_name": item_name,
        "amount": fields.get("amount_without_tax", ""),
        "tax_amount": fields.get("tax_amount", ""),
        "total_amount": fields.get("total_amount", ""),
    }
    if tax_rate := _extract_tax_rate(text):
        item["tax_rate"] = tax_rate
    return [item]


def _evaluate_invariants(fields: dict[str, Any], line_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    invariants: list[dict[str, Any]] = []
    amount = _to_money(fields.get("amount_without_tax"))
    tax = _to_money(fields.get("tax_amount"))
    total = _to_money(fields.get("total_amount"))
    if amount is not None and tax is not None and total is not None:
        passed = abs(round(amount + tax - total, 2)) <= 0.01
        invariants.append(
            {
                "id": "vat.amount_tax_total_equation",
                "status": "pass" if passed else "fail",
                "required": True,
                "details": {
                    "amount_without_tax": amount,
                    "tax_amount": tax,
                    "total_amount": total,
                    "expected_total": round(amount + tax, 2),
                },
            }
        )
    else:
        invariants.append(
            {
                "id": "vat.amount_tax_total_equation",
                "status": "fail",
                "required": True,
                "details": {"reason": "missing_amount_fields"},
            }
        )
    invariants.append(
        {
            "id": "vat.core_field_coverage",
            "status": "pass" if _field_coverage(fields) >= 0.7 else "warn",
            "required": False,
            "details": {"coverage": round(_field_coverage(fields), 4)},
        }
    )
    invariants.append(
        {
            "id": "vat.line_item_presence",
            "status": "pass" if line_items else "warn",
            "required": False,
            "details": {"line_items": len(line_items)},
        }
    )
    return invariants


def _summary(fields: dict[str, Any], line_items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_rows": len(line_items),
        "amount_without_tax": fields.get("amount_without_tax", ""),
        "tax_amount": fields.get("tax_amount", ""),
        "total_amount": fields.get("total_amount", ""),
    }


def _field_coverage(fields: dict[str, Any]) -> float:
    required = (
        "invoice_code",
        "invoice_number",
        "issue_date",
        "buyer_name",
        "buyer_tax_id",
        "seller_name",
        "seller_tax_id",
        "amount_without_tax",
        "tax_amount",
        "total_amount",
    )
    return sum(1 for key in required if fields.get(key)) / len(required)


def _put_match(fields: dict[str, Any], key: str, match: re.Match[str] | None) -> None:
    if match:
        fields[key] = match.group("value").strip()


def _money_values(text: str) -> list[float]:
    values: list[float] = []
    for m in _MONEY_RE.finditer(text):
        try:
            values.append(float(f"{m.group(1).replace(',', '')}.{m.group(2)}"))
        except ValueError:
            continue
    return values


def _money_after(text: str, marker: str) -> float | None:
    idx = text.find(marker)
    if idx < 0:
        return None
    m = _MONEY_RE.search(text[idx:])
    if not m:
        return None
    return float(f"{m.group(1).replace(',', '')}.{m.group(2)}")


def _amount_tax_pair(values: list[float], total: float) -> tuple[float, float] | None:
    candidates = [value for value in values if abs(value - total) > 0.01]
    best: tuple[float, float] | None = None
    for idx, left in enumerate(candidates):
        for right in candidates[idx + 1 :]:
            if abs(round(left + right - total, 2)) <= 0.01:
                amount = max(left, right)
                tax = min(left, right)
                pair = (amount, tax)
                if best is None or pair[0] > best[0]:
                    best = pair
    return best


def _fmt_money(value: float) -> str:
    return f"{value:.2f}"


def _to_money(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "").replace("¥", "").replace("￥", ""))
    except ValueError:
        return None


def _line_after_marker(text: str, marker: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for idx, line in enumerate(lines):
        if marker in line and idx + 1 < len(lines):
            return lines[idx + 1].strip()
    return ""


def _line_value(text: str, marker: str) -> str:
    for line in (text or "").splitlines():
        if marker in line and ":" in line:
            return line.split(":", 1)[1].strip()
        if marker in line and "：" in line:
            return line.split("：", 1)[1].strip()
    return ""


def _inline_label_value(text: str, marker: str) -> str:
    stop = r"(?:收款人|复核|开票人|销售方|购买方|发票专用章|$)"
    pattern = re.compile(rf"{re.escape(marker)}[:：]\s*(?P<value>.*?)(?=\s+{stop}|{stop})")
    matches = [m.group("value").strip() for m in pattern.finditer(text or "")]
    values = [value for value in matches if value and value != marker]
    if values:
        return _clean_short_value(values[-1])
    return _clean_short_value(_line_value(text, marker))


def _extract_tax_rate(text: str) -> str:
    m = re.search(r"(?<!\d)(\d{1,2})\s*[%％]", text)
    return f"{m.group(1)}%" if m else ""


def _clean_company_name(value: str) -> str:
    value = _clean_short_value(value)
    if match := re.search(r"[\u4e00-\u9fa5A-Za-z0-9()（）·]+有限公司", value):
        return match.group(0)
    return value


def _clean_address_phone(value: str) -> str:
    value = _clean_short_value(value)
    phone_match = re.search(r"(.+?(?:1\d{10}|0\d{2,4}[- ]?\d{7,8}))", value)
    if phone_match:
        return phone_match.group(1).strip(" 、,，")
    return value


def _clean_bank_account(value: str) -> str:
    value = _clean_short_value(value)
    account_match = re.search(r"(.+?、\s*\d{6,30})", value)
    if account_match:
        return account_match.group(1).strip(" 、,，")
    return value


def _clean_short_value(value: str) -> str:
    value = str(value or "").strip()
    value = re.sub(r"\s+", " ", value)
    return value.strip(" ：:、,，")


__all__ = ["VATInvoiceSemanticSolver"]
