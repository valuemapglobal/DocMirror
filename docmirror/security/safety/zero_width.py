# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Zero-Width Character Detector — Detect and sanitize zero-width characters.

Zero-width characters (U+200B, U+200C, U+FEFF, U+2060–U+2069, etc.) are
invisible in rendered text but can be used to smuggle prompt-injection
payloads past string-based safety filters.

The detector scans all extracted text and can either flag or remove
these characters depending on the configured strictness level.
"""

from __future__ import annotations

from dataclasses import dataclass

# ── Zero-width character catalog ──────────────────────────────────────────

ZERO_WIDTH_CHARS: dict[str, str] = {
    "\u200b": "ZERO_WIDTH_SPACE",
    "\u200c": "ZERO_WIDTH_NON_JOINER",
    "\u200d": "ZERO_WIDTH_JOINER",
    "\u200e": "LEFT_TO_RIGHT_MARK",
    "\u200f": "RIGHT_TO_LEFT_MARK",
    "\ufeff": "BOM_ZERO_WIDTH_NO_BREAK_SPACE",
    "\u2060": "WORD_JOINER",
    "\u2061": "FUNCTION_APPLICATION",
    "\u2062": "INVISIBLE_TIMES",
    "\u2063": "INVISIBLE_SEPARATOR",
    "\u2064": "INVISIBLE_PLUS",
    "\u2066": "LEFT_TO_RIGHT_ISOLATE",
    "\u2067": "RIGHT_TO_LEFT_ISOLATE",
    "\u2068": "FIRST_STRONG_ISOLATE",
    "\u2069": "POP_DIRECTIONAL_ISOLATE",
}

SANITIZE_MAP: dict[str, str] = {
    # Replace visible-adjacent zero-width chars with space
    "\u200b": "",
    "\u200c": "",
    "\u200d": "",
    "\ufeff": "",
    "\u2060": "",
    "\u2061": "",
    "\u2062": "",
    "\u2063": "",
    "\u2064": "",
    # Directional isolates — replace with space to preserve layout
    "\u2066": "",
    "\u2067": "",
    "\u2068": "",
    "\u2069": "",
    # Directional marks — replace with space
    "\u200e": "",
    "\u200f": "",
}


@dataclass
class ZeroWidthFlag:
    """A single zero-width character finding."""

    char: str = ""
    char_name: str = ""
    position: int = 0
    context: str = ""


# ── Detector ──────────────────────────────────────────────────────────────


class ZeroWidthDetector:
    """Detect and sanitize zero-width characters in document text.

    Usage::

        detector = ZeroWidthDetector()
        flags = detector.detect("hello\\u200Bworld")
        clean = detector.sanitize("hello\\u200Bworld")
    """

    def detect(self, text: str) -> list[ZeroWidthFlag]:
        """Find all zero-width characters in *text*.

        Args:
            text: Full document text to scan.

        Returns:
            List of ``ZeroWidthFlag`` for each zero-width character found.
        """
        flags: list[ZeroWidthFlag] = []
        for pos, char in enumerate(text):
            if char in ZERO_WIDTH_CHARS:
                start = max(0, pos - 20)
                end = min(len(text), pos + 20)
                context = text[start:end]
                flags.append(
                    ZeroWidthFlag(
                        char=char,
                        char_name=ZERO_WIDTH_CHARS[char],
                        position=pos,
                        context=context,
                    )
                )
        return flags

    def sanitize(self, text: str, *, mode: str = "remove") -> str:
        """Remove or replace zero-width characters in *text*.

        Args:
            text: Text to sanitize.
            mode: ``"remove"`` (default) strips all zero-width chars;
                ``"replace"`` replaces them with a space character.

        Returns:
            Sanitized text string.
        """
        if mode == "remove":
            trans_table = str.maketrans({c: None for c in SANITIZE_MAP})
            return text.translate(trans_table)
        elif mode == "replace":
            trans_table = str.maketrans(SANITIZE_MAP)
            return text.translate(trans_table)
        else:
            msg = f"Unknown sanitize mode: {mode!r} (expected 'remove' or 'replace')"
            raise ValueError(msg)

    def count(self, text: str) -> int:
        """Count zero-width characters in *text* (quick check)."""
        return sum(1 for c in text if c in ZERO_WIDTH_CHARS)


__all__ = [
    "ZERO_WIDTH_CHARS",
    "SANITIZE_MAP",
    "ZeroWidthDetector",
    "ZeroWidthFlag",
]
