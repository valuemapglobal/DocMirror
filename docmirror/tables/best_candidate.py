# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Best candidate picker — scores and selects among extraction candidates.

Purpose: Implements BCS (best-candidate selection) scoring using column
consistency, header vocabulary match, and data-row counts.

Main components: ``pick_best_candidate``, ``score_candidate``,
``ExtractCandidate``, ``BCSPickResult``.

Upstream: Multiple ``extract.engine`` tier outputs.

Downstream: ``extract.engine`` final table choice, ``extract.classifier``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from docmirror.layout.vocabulary import _is_header_cell, _score_header_by_vocabulary

if TYPE_CHECKING:
    from docmirror.models.entities.extraction_profile import ExtractionProfile

logger = logging.getLogger(__name__)

_LAYER_PRIOR: dict[str, float] = {
    "pdfplumber_default": 1.0,
    "text": 0.85,
    "lines": 0.80,
    "pipe_delimited": 0.75,
    "signal_processor": 0.70,
    "header_anchors": 0.65,
    "header_guided": 0.65,
    "grid_reconstructor": 0.80,
    "word_anchors": 0.65,
    "data_voting": 0.65,
    "whitespace_projection": 0.60,
    "pymupdf_native": 0.50,
    "template_injection": 0.99,
    "fallback": 0.30,
}

_CHAR_LAYERS = frozenset(
    {
        "header_anchors",
        "header_guided",
        "grid_reconstructor",
        "word_anchors",
        "data_voting",
        "whitespace_projection",
        "x_clustering",
    }
)
_DATE_RE = re.compile(r"(?:19|20)\d{2}[-/.]\d{1,2}[-/.]\d{1,2}|(?:19|20)\d{6}")
_AMOUNT_RE = re.compile(r"^[+-]?\d[\d,]*(?:\.\d+)?$")


@dataclass
class ExtractCandidate:
    """One table extraction attempt from a specific engine layer."""

    tables: list[list[list[str]]]
    layer: str
    confidence: float
    row_count: int = 0
    col_count: int = 0

    def __post_init__(self) -> None:
        if self.tables and self.tables[0]:
            self.row_count = len(self.tables[0])
            self.col_count = len(self.tables[0][0]) if self.tables[0] else 0


@dataclass
class BCSPickResult:
    candidate: ExtractCandidate
    score: float
    oracle_rows: int = 0
    all_candidates: list[ExtractCandidate] = field(default_factory=list)


def _col_consistency(tbl: list[list[str]]) -> float:
    if not tbl or len(tbl) < 2:
        return 1.0 if tbl else 0.0
    expected = len(tbl[0])
    if expected == 0:
        return 0.0
    matching = sum(1 for row in tbl[1:] if len(row) == expected)
    return matching / max(len(tbl) - 1, 1)


def _header_vocab_score(tbl: list[list[str]], expected_headers: list[str]) -> float:
    if not tbl or not expected_headers:
        return 0.0
    header = [str(c or "").strip() for c in tbl[0]]
    if not header:
        return 0.0
    hits = 0
    for exp in expected_headers:
        exp_norm = exp.strip()
        if any(exp_norm in h or h in exp_norm for h in header if h):
            hits += 1
    return hits / len(expected_headers)


def _ledger_logical_row_quality(tbl: list[list[str]]) -> float:
    """Estimate how many body rows are real logical ledger rows, not fragments."""
    if not tbl or len(tbl) < 2:
        return 0.0
    body = tbl[1:]
    if not body:
        return 0.0
    width = max(len(tbl[0]), 1)
    min_populated = max(3, min(width, (width + 1) // 2))
    paired = 0
    populated = 0
    density_sum = 0.0
    for row in body:
        cells = [str(c or "").strip() for c in row]
        non_empty = sum(1 for c in cells if c)
        density_sum += non_empty / width
        has_date = any(_DATE_RE.search(c) for c in cells)
        has_amount = any(_AMOUNT_RE.match(c.replace(",", "").replace("¥", "").replace("￥", "")) for c in cells)
        if has_date and has_amount:
            paired += 1
        if non_empty >= min_populated:
            populated += 1
    pair_ratio = paired / len(body)
    populated_ratio = populated / len(body)
    density = density_sum / len(body)
    fallback_quality = 0.6 * populated_ratio + 0.4 * min(1.0, density * 1.25)
    if pair_ratio < 0.25:
        fallback_quality *= 0.5
    return max(pair_ratio, fallback_quality)


def score_candidate(
    candidate: ExtractCandidate,
    *,
    profile: ExtractionProfile,
    oracle_rows: int = 0,
) -> float:
    """Weighted score 0–1 for BCS."""
    tbl = candidate.tables[0] if candidate.tables else []
    if not tbl:
        return 0.0

    # Oracle-row penalty: when the oracle (pdfplumber_default) finds few rows
    # for borderless tables, char-level methods like CSP find 10-50x more rows.
    # The original oracle penalty (row_ratio = oracle/candidate) would penalize
    # better extraction.  For char-level methods: more rows = better.
    if oracle_rows > 0:
        if candidate.layer in _CHAR_LAYERS:
            row_quality = _ledger_logical_row_quality(tbl) if profile.is_borderless_ledger() else 1.0
            effective_rows = candidate.row_count * max(0.05, row_quality)
            row_ratio = min(1.0, effective_rows / max(oracle_rows, 50))
        elif candidate.row_count > oracle_rows:
            row_ratio = oracle_rows / candidate.row_count
        else:
            row_ratio = candidate.row_count / oracle_rows
    else:
        row_ratio = min(1.0, candidate.row_count / 50.0)
    col_cons = _col_consistency(tbl)
    header_vocab = _header_vocab_score(tbl, profile.expected_header_columns)
    expected_cols = profile.expected_header_columns
    col_match = 1.0 if expected_cols and candidate.col_count == len(expected_cols) else 0.5
    layer_prior = _LAYER_PRIOR.get(candidate.layer, 0.5)

    if candidate.layer == "template_injection" and oracle_rows > 0 and candidate.row_count > oracle_rows * 1.03:
        layer_prior = min(layer_prior, 0.55)

    preferred = profile.table_preferred_layers()
    if preferred and candidate.layer in preferred:
        idx = preferred.index(candidate.layer)
        layer_prior = max(layer_prior, 1.0 - idx * 0.05)

    if candidate.layer == "pipe_delimited" and (
        profile.is_borderless_ledger() or (preferred and preferred[0] == "pipe_delimited")
    ):
        layer_prior = max(layer_prior, 1.0)

    return 0.35 * row_ratio + 0.25 * col_cons + 0.20 * header_vocab + 0.10 * col_match + 0.10 * layer_prior


def pick_best_candidate(
    candidates: list[ExtractCandidate],
    profile: ExtractionProfile,
    *,
    oracle_rows: int = 0,
) -> BCSPickResult | None:
    """Select the highest-scoring extraction candidate."""
    if not candidates:
        return None

    scored = [(score_candidate(c, profile=profile, oracle_rows=oracle_rows), c) for c in candidates]

    def _sort_key(item: tuple[float, ExtractCandidate]) -> tuple:
        score, c = item
        oracle_dist = -abs(c.row_count - oracle_rows) if oracle_rows > 0 else 0
        return (score, oracle_dist, c.confidence, _LAYER_PRIOR.get(c.layer, 0.0))

    scored.sort(key=_sort_key, reverse=True)
    best_score, best = scored[0]
    for s, c in scored[:6]:
        logger.info(
            "[BCS-DBG] layer=%s rows=%d cols=%d score=%.4f",
            c.layer,
            c.row_count,
            getattr(c, "col_count", 0),
            s,
        )
    logger.debug(
        "[BCS] picked layer=%s rows=%d score=%.3f (from %d candidates)",
        best.layer,
        best.row_count,
        best_score,
        len(candidates),
    )
    return BCSPickResult(
        candidate=best,
        score=best_score,
        oracle_rows=oracle_rows,
        all_candidates=list(candidates),
    )


def count_data_rows(tbl: list[list[str]]) -> int:
    """Count non-header rows in a table."""
    if not tbl:
        return 0
    if _is_header_cell(str(tbl[0][0] if tbl[0] else "")) or _score_header_by_vocabulary(tbl[0]) >= 3:
        return max(0, len(tbl) - 1)
    return len(tbl)
