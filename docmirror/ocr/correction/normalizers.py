# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Script-aware Unicode normalization registry for OCR correction."""

from __future__ import annotations

import re
import unicodedata
from typing import Protocol

_CONTROL_RE = re.compile(r"[\u200b-\u200f\u2028-\u202f\ufeff]")
_SPACE_RE = re.compile(r"[ \t]+")


class TextNormalizer(Protocol):
    def normalize(self, text: str) -> str: ...


class UnicodeTextNormalizer:
    def __init__(self, form: str = "NFKC") -> None:
        self.form = form

    def normalize(self, text: str) -> str:
        normalized = unicodedata.normalize(self.form, str(text or ""))
        normalized = _CONTROL_RE.sub("", normalized)
        normalized = _SPACE_RE.sub(" ", normalized)
        return normalized.strip()


class NormalizerRegistry:
    def __init__(self) -> None:
        self._normalizers: dict[str, TextNormalizer] = {}
        self._fallback: TextNormalizer = UnicodeTextNormalizer("NFKC")

    def register(self, key: str, normalizer: TextNormalizer) -> None:
        self._normalizers[str(key).lower()] = normalizer

    def resolve(self, *, language: str | None = None, script: str | None = None) -> TextNormalizer:
        return self._normalizers.get(str(language or "").lower()) or self._normalizers.get(
            str(script or "").lower(), self._fallback
        )

    @classmethod
    def default(cls) -> NormalizerRegistry:
        registry = cls()
        canonical = UnicodeTextNormalizer("NFC")
        for key in ("ar", "arabic", "th", "thai", "hi", "devanagari"):
            registry.register(key, canonical)
        # CJK and Latin OCR commonly benefit from full-width/compatibility folding.
        compatibility = UnicodeTextNormalizer("NFKC")
        for key in ("zh", "ja", "ko", "han", "hiragana", "katakana", "hangul", "latin"):
            registry.register(key, compatibility)
        return registry


__all__ = ["NormalizerRegistry", "TextNormalizer", "UnicodeTextNormalizer"]
