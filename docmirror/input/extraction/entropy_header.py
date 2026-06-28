# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Entropy helpers for table header inference."""

from __future__ import annotations

import math
import re
from collections import Counter


class EntropyHeaderDetector:
    """Small dependency-free detector used by HeaderInferrerMiddleware."""

    def calculate_entropy(self, values: list[str]) -> float:
        tokens = [str(value or "").strip() for value in values if str(value or "").strip()]
        if not tokens:
            return 0.0
        counts = Counter(_value_class(token) for token in tokens)
        total = sum(counts.values())
        entropy = -sum((count / total) * math.log2(count / total) for count in counts.values())
        max_entropy = math.log2(max(2, len(counts)))
        return min(1.0, entropy / max_entropy) if max_entropy else 0.0

    def analyze_type_consistency(self, rows: list[list[str]]) -> float:
        if not rows:
            return 0.0
        column_count = max((len(row) for row in rows), default=0)
        if column_count <= 0:
            return 0.0
        scores: list[float] = []
        for col_index in range(column_count):
            classes = [
                _value_class(row[col_index])
                for row in rows
                if col_index < len(row) and str(row[col_index] or "").strip()
            ]
            if len(classes) < 2:
                continue
            counts = Counter(classes)
            scores.append(max(counts.values()) / len(classes))
        return sum(scores) / len(scores) if scores else 0.0


def _value_class(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "empty"
    cleaned = text.replace(",", "").replace("，", "")
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", cleaned):
        return "number"
    if re.search(r"\d{4}[-/年]\d{1,2}", text):
        return "date"
    if re.search(r"[\u4e00-\u9fff]", text):
        return "cjk_text"
    if re.search(r"[A-Za-z]", text):
        return "latin_text"
    return "symbol"
