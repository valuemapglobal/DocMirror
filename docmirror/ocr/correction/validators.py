# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deterministic validators used as hard gates for OCR correction."""

from __future__ import annotations

import itertools
import re
from datetime import date
from decimal import Decimal, InvalidOperation

_USCC_CHARSET = "0123456789ABCDEFGHJKLMNPQRTUWXY"
_USCC_WEIGHTS = (1, 3, 9, 27, 19, 26, 16, 17, 20, 29, 25, 13, 8, 24, 10, 30, 28)
_USCC_OPTIONS = {
    "O": ("O", "0"),
    "I": ("I", "1"),
    "L": ("L", "1"),
    "Z": ("Z", "2"),
    "S": ("S", "5"),
    "B": ("B", "8"),
    "0": ("0", "O"),
    "1": ("1", "I", "L"),
    "2": ("2", "Z"),
    "5": ("5", "S"),
    "8": ("8", "B"),
}
_AMOUNT_RE = re.compile(r"^[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?$")
_BIC_RE = re.compile(r"^[A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?$")
_EU_VAT_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{2,12}$")
_EIN_RE = re.compile(r"^\d{2}-?\d{7}$")
_JP_CORPORATE_NUMBER_RE = re.compile(r"^\d{13}$")
_SG_UEN_RE = re.compile(r"^(?:\d{8}[A-Z]|\d{9}[A-Z]|[STF]\d{2}[A-Z]{2}\d{4}[A-Z])$")
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_PHONE_RE = re.compile(r"^\+?[0-9][0-9 ()-]{5,20}$")
_CN_RESIDENT_ID_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
_CN_RESIDENT_ID_CHECKS = "10X98765432"


def validate_uscc(code: str) -> bool:
    """Validate a unified social credit code using GB 32100-2015."""
    normalized = re.sub(r"\s+", "", str(code or "")).upper()
    if len(normalized) != 18 or any(char not in _USCC_CHARSET for char in normalized):
        return False
    total = sum(_USCC_CHARSET.index(char) * _USCC_WEIGHTS[index] for index, char in enumerate(normalized[:17]))
    expected = _USCC_CHARSET[(31 - total % 31) % 31]
    return normalized[-1] == expected


def validate_cn_resident_id(value: str) -> bool:
    """Validate an 18-character PRC resident identity number.

    The date segment and GB 11643 checksum must both be valid. Whitespace and
    hyphens introduced by OCR/layout reconstruction are ignored.
    """
    normalized = re.sub(r"[\s-]+", "", str(value or "")).upper()
    if not re.fullmatch(r"\d{17}[\dX]", normalized):
        return False
    try:
        date(int(normalized[6:10]), int(normalized[10:12]), int(normalized[12:14]))
    except ValueError:
        return False
    checksum_index = sum(int(char) * weight for char, weight in zip(normalized[:17], _CN_RESIDENT_ID_WEIGHTS)) % 11
    return normalized[-1] == _CN_RESIDENT_ID_CHECKS[checksum_index]


def repair_uscc_if_unique(code: str, *, max_variants: int = 4096) -> str | None:
    """Return a checksum-valid OCR variant only when it is unique."""
    normalized = re.sub(r"\s+", "", str(code or "")).upper()
    if len(normalized) != 18:
        return None
    if validate_uscc(normalized):
        return normalized

    choices: list[tuple[str, ...]] = []
    variant_count = 1
    for char in normalized:
        options = tuple(dict.fromkeys(_USCC_OPTIONS.get(char, (char,))))
        options = tuple(option for option in options if option in _USCC_CHARSET)
        if not options:
            return None
        choices.append(options)
        variant_count *= len(options)
        if variant_count > max_variants:
            return None

    valid: list[str] = []
    for chars in itertools.product(*choices):
        candidate = "".join(chars)
        if candidate == normalized:
            continue
        if validate_uscc(candidate):
            valid.append(candidate)
            if len(valid) > 1:
                return None
    return valid[0] if len(valid) == 1 else None


def validate_date_text(value: str) -> bool:
    text = str(value or "").strip()
    match = re.fullmatch(r"((?:19|20)\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})日?", text)
    if not match:
        return False
    try:
        date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return False
    return True


def validate_amount_text(value: str) -> bool:
    text = str(value or "").strip().replace("￥", "").replace("¥", "")
    if not _AMOUNT_RE.fullmatch(text):
        return False
    try:
        Decimal(text.replace(",", ""))
    except InvalidOperation:
        return False
    return True


def validate_iban(value: str) -> bool:
    """Validate an IBAN using its ISO 13616 mod-97 check digits."""
    text = re.sub(r"\s+", "", str(value or "")).upper()
    if not 15 <= len(text) <= 34 or not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]+", text):
        return False
    rearranged = text[4:] + text[:4]
    remainder = 0
    for char in rearranged:
        digits = str(ord(char) - 55) if char.isalpha() else char
        for digit in digits:
            remainder = (remainder * 10 + int(digit)) % 97
    return remainder == 1


def repair_iban_if_unique(value: str, *, max_variants: int = 4096) -> str | None:
    normalized = re.sub(r"\s+", "", str(value or "")).upper()
    if validate_iban(normalized):
        return normalized
    valid: list[str] = []
    variant_count = 0
    # A single-glyph repair is deliberately conservative. Trying the full
    # Cartesian product over an IBAN produces many checksum-valid alternatives.
    for index, char in enumerate(normalized):
        for replacement in dict.fromkeys(_USCC_OPTIONS.get(char, (char,))):
            if replacement == char:
                continue
            if index < 2 and not replacement.isalpha():
                continue
            if 2 <= index < 4 and not replacement.isdigit():
                continue
            if index >= 4 and not replacement.isalnum():
                continue
            variant_count += 1
            if variant_count > max_variants:
                return None
            candidate = f"{normalized[:index]}{replacement}{normalized[index + 1 :]}"
            if validate_iban(candidate):
                valid.append(candidate)
                if len(valid) > 1:
                    return None
    return valid[0] if len(valid) == 1 else None


def validate_bic(value: str) -> bool:
    return bool(_BIC_RE.fullmatch(re.sub(r"\s+", "", str(value or "")).upper()))


def validate_eu_vat_format(value: str) -> bool:
    return bool(_EU_VAT_RE.fullmatch(re.sub(r"[\s.-]+", "", str(value or "")).upper()))


def validate_us_ein_format(value: str) -> bool:
    return bool(_EIN_RE.fullmatch(str(value or "").strip()))


def validate_jp_corporate_number_format(value: str) -> bool:
    return bool(_JP_CORPORATE_NUMBER_RE.fullmatch(re.sub(r"\s+", "", str(value or ""))))


def validate_sg_uen_format(value: str) -> bool:
    return bool(_SG_UEN_RE.fullmatch(re.sub(r"\s+", "", str(value or "")).upper()))


def validate_email_text(value: str) -> bool:
    return bool(_EMAIL_RE.fullmatch(str(value or "").strip()))


def validate_phone_text(value: str) -> bool:
    return bool(_PHONE_RE.fullmatch(str(value or "").strip()))


__all__ = [
    "repair_uscc_if_unique",
    "repair_iban_if_unique",
    "validate_amount_text",
    "validate_bic",
    "validate_cn_resident_id",
    "validate_date_text",
    "validate_email_text",
    "validate_eu_vat_format",
    "validate_iban",
    "validate_jp_corporate_number_format",
    "validate_phone_text",
    "validate_sg_uen_format",
    "validate_us_ein_format",
    "validate_uscc",
]
