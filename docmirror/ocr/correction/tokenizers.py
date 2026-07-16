# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Small script-aware tokenizer registry used by deterministic correction."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Token:
    text: str
    start: int
    end: int


class CorrectionTokenizer(Protocol):
    def tokenize(self, text: str) -> list[Token]: ...


class RegexTokenizer:
    def __init__(self, pattern: str) -> None:
        self._pattern = re.compile(pattern)

    def tokenize(self, text: str) -> list[Token]:
        return [Token(match.group(0), match.start(), match.end()) for match in self._pattern.finditer(str(text or ""))]


class CJKTokenizer(RegexTokenizer):
    def __init__(self) -> None:
        super().__init__(r"[\u3400-\u9fff]+|[A-Za-z0-9]+")


class JapaneseTokenizer(RegexTokenizer):
    def __init__(self) -> None:
        super().__init__(r"[\u3040-\u30ff\u3400-\u9fff]+|[A-Za-z0-9]+")


class LatinTokenizer(RegexTokenizer):
    def __init__(self) -> None:
        super().__init__(
            r"[^\W_]+(?:[-'][^\W_]+)*|\d+",
        )


class ArabicTokenizer(RegexTokenizer):
    def __init__(self) -> None:
        super().__init__(r"[\u0600-\u06ff\u0750-\u077f]+|[A-Za-z0-9]+")


class ThaiTokenizer(RegexTokenizer):
    def __init__(self) -> None:
        super().__init__(r"[\u0e00-\u0e7f]+|[A-Za-z0-9]+")


class GenericUnicodeTokenizer(RegexTokenizer):
    def __init__(self) -> None:
        super().__init__(
            r"[^\W_]+",
        )


class TokenizerRegistry:
    def __init__(self) -> None:
        self._tokenizers: dict[str, CorrectionTokenizer] = {}
        self._fallback: CorrectionTokenizer = GenericUnicodeTokenizer()

    def register(self, key: str, tokenizer: CorrectionTokenizer) -> None:
        self._tokenizers[str(key).lower()] = tokenizer

    def resolve(self, *, language: str | None = None, script: str | None = None) -> CorrectionTokenizer:
        return self._tokenizers.get(str(language or "").lower()) or self._tokenizers.get(
            str(script or "").lower(), self._fallback
        )

    @classmethod
    def default(cls) -> TokenizerRegistry:
        registry = cls()
        latin = LatinTokenizer()
        for key in ("en", "de", "fr", "es", "it", "pt", "latin"):
            registry.register(key, latin)
        cjk = CJKTokenizer()
        registry.register("zh", cjk)
        registry.register("han", cjk)
        registry.register("ja", JapaneseTokenizer())
        registry.register("hiragana", JapaneseTokenizer())
        registry.register("katakana", JapaneseTokenizer())
        registry.register("ar", ArabicTokenizer())
        registry.register("arabic", ArabicTokenizer())
        registry.register("th", ThaiTokenizer())
        registry.register("thai", ThaiTokenizer())
        return registry


__all__ = [
    "ArabicTokenizer",
    "CJKTokenizer",
    "CorrectionTokenizer",
    "GenericUnicodeTokenizer",
    "JapaneseTokenizer",
    "LatinTokenizer",
    "ThaiTokenizer",
    "Token",
    "TokenizerRegistry",
]
