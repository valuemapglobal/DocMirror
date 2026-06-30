"""Dependency-free hybrid text matcher helpers."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

_UNICODE_EQUIV = {
    "α": "a",
    "β": "b",
    "γ": "g",
    "∫": "\\int",
}


def normalize_unicode(text: str) -> str:
    out = "".join(_UNICODE_EQUIV.get(char, char) for char in text)
    return unicodedata.normalize("NFKC", out)


def is_latex_equivalent(left: str, right: str) -> bool:
    return _normalize_latex(left) == _normalize_latex(right)


def fuzzy_segment_match(left: str, right: str, *, threshold: float = 0.86) -> bool:
    return SequenceMatcher(None, normalize_unicode(left), normalize_unicode(right)).ratio() >= threshold


def hybrid_match(left: str, right: str) -> bool:
    left_norm = normalize_unicode(left)
    right_norm = normalize_unicode(right)
    return left_norm == right_norm or is_latex_equivalent(left_norm, right_norm) or fuzzy_segment_match(left_norm, right_norm)


def _normalize_latex(text: str) -> str:
    text = normalize_unicode(text)
    text = text.replace("\\dfrac", "\\frac")
    text = text.replace("\\left", "").replace("\\right", "")
    text = re.sub(r"\s+", "", text)
    return text
