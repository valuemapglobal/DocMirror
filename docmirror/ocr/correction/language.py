# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Dependency-free language, locale, and Unicode script hints for OCR text."""

from __future__ import annotations

import re
from dataclasses import dataclass

_LANGUAGE_RE = re.compile(r"^[A-Za-z]{2,3}$")
_COUNTRY_RE = re.compile(r"^[A-Za-z]{2}$")
_LOCALE_RE = re.compile(r"^([A-Za-z]{2,3})(?:[-_]([A-Za-z]{2}))?$")


@dataclass(frozen=True)
class LanguageHint:
    language: str | None = None
    country: str | None = None
    locale: str | None = None
    script: str | None = None
    confidence: float = 0.0


def normalize_language(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if not _LANGUAGE_RE.fullmatch(text):
        raise ValueError(f"invalid OCR language: {value!r}")
    return text.lower()


def normalize_country(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if not _COUNTRY_RE.fullmatch(text):
        raise ValueError(f"invalid OCR country: {value!r}")
    return text.upper()


def normalize_locale(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = _LOCALE_RE.fullmatch(text)
    if not match:
        raise ValueError(f"invalid OCR locale: {value!r}")
    language = match.group(1).lower()
    country = match.group(2)
    return f"{language}-{country.upper()}" if country else language


def resolve_language_hint(
    text: str,
    *,
    language: str | None = None,
    country: str | None = None,
    locale: str | None = None,
    script: str | None = None,
) -> LanguageHint:
    resolved_locale = normalize_locale(locale)
    locale_language, locale_country = _split_locale(resolved_locale)
    explicit_language = normalize_language(language)
    explicit_country = normalize_country(country)
    if explicit_language and locale_language and explicit_language != locale_language:
        raise ValueError(f"OCR language {explicit_language!r} conflicts with locale {resolved_locale!r}")
    if explicit_country and locale_country and explicit_country != locale_country:
        raise ValueError(f"OCR country {explicit_country!r} conflicts with locale {resolved_locale!r}")
    resolved_language = explicit_language or locale_language
    resolved_country = explicit_country or locale_country
    detected_script, script_confidence = detect_script(text)
    resolved_script = str(script or "").strip() or detected_script
    if resolved_language is None:
        resolved_language = _language_for_script(resolved_script, text)
    if resolved_locale is None and resolved_language and resolved_country:
        resolved_locale = f"{resolved_language}-{resolved_country}"
    confidence = 1.0 if language or locale else script_confidence
    return LanguageHint(
        language=resolved_language,
        country=resolved_country,
        locale=resolved_locale,
        script=resolved_script,
        confidence=confidence,
    )


def detect_script(text: str) -> tuple[str | None, float]:
    counts: dict[str, int] = {}
    for char in str(text or ""):
        script = _char_script(char)
        if script:
            counts[script] = counts.get(script, 0) + 1
    if not counts:
        return None, 0.0
    script, count = max(counts.items(), key=lambda item: (item[1], item[0]))
    return script, count / max(1, sum(counts.values()))


def _char_script(char: str) -> str | None:
    code = ord(char)
    if 0x4E00 <= code <= 0x9FFF or 0x3400 <= code <= 0x4DBF:
        return "Han"
    if 0x3040 <= code <= 0x309F:
        return "Hiragana"
    if 0x30A0 <= code <= 0x30FF or 0x31F0 <= code <= 0x31FF:
        return "Katakana"
    if 0xAC00 <= code <= 0xD7AF or 0x1100 <= code <= 0x11FF:
        return "Hangul"
    if 0x0600 <= code <= 0x06FF or 0x0750 <= code <= 0x077F:
        return "Arabic"
    if 0x0400 <= code <= 0x052F:
        return "Cyrillic"
    if 0x0E00 <= code <= 0x0E7F:
        return "Thai"
    if 0x0900 <= code <= 0x097F:
        return "Devanagari"
    if char.isascii() and char.isalpha():
        return "Latin"
    if char.isalpha():
        return "Latin"
    return None


def _language_for_script(script: str | None, text: str) -> str | None:
    if script in {"Hiragana", "Katakana"}:
        return "ja"
    if script == "Hangul":
        return "ko"
    if script == "Arabic":
        return "ar"
    if script == "Thai":
        return "th"
    if script == "Devanagari":
        return "hi"
    if script == "Han":
        if any(0x3040 <= ord(char) <= 0x30FF for char in text):
            return "ja"
        return "zh"
    # Latin and Cyrillic scripts do not uniquely identify a language.
    return None


def _split_locale(locale: str | None) -> tuple[str | None, str | None]:
    if not locale:
        return None, None
    parts = locale.split("-", 1)
    return parts[0], parts[1] if len(parts) == 2 else None


__all__ = [
    "LanguageHint",
    "detect_script",
    "normalize_country",
    "normalize_language",
    "normalize_locale",
    "resolve_language_hint",
]
