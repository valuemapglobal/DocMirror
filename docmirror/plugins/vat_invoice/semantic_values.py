# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Text and monetary value helpers for the VAT semantic solver."""

from __future__ import annotations

import re
from typing import Any

_MONEY_RE = re.compile(r"[¥￥]?\s*(\d{1,3}(?:,\d{3})*|\d+)\.(\d{2})")


def put_match(fields: dict[str, Any], key: str, match: re.Match[str] | None) -> None:
    if match:
        fields[key] = match.group("value").strip()


def money_values(text: str) -> list[float]:
    values: list[float] = []
    for match in _MONEY_RE.finditer(text):
        try:
            values.append(float(f"{match.group(1).replace(',', '')}.{match.group(2)}"))
        except ValueError:
            continue
    return values


def money_after(text: str, marker: str) -> float | None:
    index = text.find(marker)
    if index < 0:
        return None
    match = _MONEY_RE.search(text[index:])
    if not match:
        return None
    return float(f"{match.group(1).replace(',', '')}.{match.group(2)}")


def amount_tax_pair(values: list[float], total: float) -> tuple[float, float] | None:
    candidates = [value for value in values if abs(value - total) > 0.01]
    best: tuple[float, float] | None = None
    for index, left in enumerate(candidates):
        for right in candidates[index + 1 :]:
            if abs(round(left + right - total, 2)) <= 0.01:
                pair = (max(left, right), min(left, right))
                if best is None or pair[0] > best[0]:
                    best = pair
    return best


def fmt_money(value: float) -> str:
    return f"{value:.2f}"


def to_money(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "").replace("¥", "").replace("￥", ""))
    except ValueError:
        return None


def line_after_marker(text: str, marker: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if marker in line and index + 1 < len(lines):
            return lines[index + 1].strip()
    return ""


def line_value(text: str, marker: str) -> str:
    for line in (text or "").splitlines():
        if marker in line and ":" in line:
            return line.split(":", 1)[1].strip()
        if marker in line and "：" in line:
            return line.split("：", 1)[1].strip()
    return ""


def inline_label_value(text: str, marker: str) -> str:
    stop = r"(?:收款人|复核|开票人|销售方|购买方|发票专用章|$)"
    pattern = re.compile(rf"{re.escape(marker)}[:：]\s*(?P<value>.*?)(?=\s+{stop}|{stop})")
    values = [match.group("value").strip() for match in pattern.finditer(text or "")]
    values = [value for value in values if value and value != marker]
    if values:
        return clean_short_value(values[-1])
    return clean_short_value(line_value(text, marker))


def extract_tax_rate(text: str) -> str:
    match = re.search(r"(?<!\d)(\d{1,2})\s*[%％]", text)
    return f"{match.group(1)}%" if match else ""


def clean_company_name(value: str) -> str:
    value = clean_short_value(value)
    if match := re.search(r"[\u4e00-\u9fa5A-Za-z0-9()（）·]+有限公司", value):
        return match.group(0)
    return value


def clean_address_phone(value: str) -> str:
    value = clean_short_value(value)
    if match := re.search(r"(.+?(?:1\d{10}|0\d{2,4}[- ]?\d{7,8}))", value):
        return match.group(1).strip(" 、,，")
    return value


def clean_bank_account(value: str) -> str:
    value = clean_short_value(value)
    if match := re.search(r"(.+?、\s*\d{6,30})", value):
        return match.group(1).strip(" 、,，")
    return value


def clean_short_value(value: str) -> str:
    value = re.sub(r"\s+", " ", str(value or "").strip())
    return value.strip(" ：:、,，")
