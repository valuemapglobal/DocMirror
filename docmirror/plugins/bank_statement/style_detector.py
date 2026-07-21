# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Bank statement layout style detector.

Scores Mirror table structure against ``style_families.yaml`` signatures to choose
a primary ledger style (grid, compact merged, signed amount, borderless OCR, etc.)
and an ordered parser chain. Detection is structural, not bank-name-only.

Pipeline role: invoked from ``bank_statement.community_plugin`` before
``BankStyleParserRegistry.run`` selects concrete parsers.

Key exports: ``StyleDetectionResult``, ``BankStyleDetector``.

Dependencies: ``bank_statement.context.StyleContext``, YAML config under
``configs/yaml/bank_statement/style_families.yaml``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from docmirror.plugins.bank_statement.context import StyleContext
from docmirror.plugins.bank_statement.header_resolve import has_split_debit_credit_headers
from docmirror.plugins.bank_statement.institution_authority import resolve_institution_hint
from docmirror.plugins.bank_statement.styles.compact_merged import table_has_compact_ledger

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs" / "yaml" / "bank_statement" / "style_families.yaml"
_DATE_AMOUNT_CELL = re.compile(r"^\d{4}-\d{2}-\d{2}\d+\.\d{2}")
_TIME_ONLY = re.compile(r"^\d{1,2}:\d{2}:\d{2}$")


@dataclass
class StyleDetectionResult:
    primary_style: str
    secondary_styles: list[str] = field(default_factory=list)
    confidence: float = 0.0
    parser_chain: list[str] = field(default_factory=list)
    institution_hint: str | None = None
    institution_authority: str = ""


@lru_cache(maxsize=1)
def _load_config() -> dict[str, Any]:
    if not _CONFIG_PATH.is_file():
        return {"styles": {}, "default_style": "grid_standard", "institution_keywords": {}}
    with open(_CONFIG_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


class BankStyleDetector:
    """Detect bank ledger layout style from table structure (not bank name alone)."""

    MATCH_THRESHOLD = 0.55

    def detect(self, ctx: StyleContext) -> StyleDetectionResult:
        cfg = _load_config()
        styles_cfg: dict[str, Any] = cfg.get("styles") or {}
        institution_hint, institution_authority = resolve_institution_hint(
            ctx,
            cfg.get("institution_keywords") or {},
        )
        if not institution_authority and ctx.institution_authority:
            institution_authority = ctx.institution_authority

        if ctx.reconstruction and ctx.reconstruction.source == "pipe_text":
            spec = styles_cfg.get("split_debit_credit", {})
            chain = list(spec.get("parser_chain") or ["grid_standard"])
            return StyleDetectionResult(
                primary_style="split_debit_credit",
                secondary_styles=["pipe_ledger_text"],
                confidence=0.95,
                parser_chain=chain,
                institution_hint=institution_hint,
                institution_authority=institution_authority,
            )

        scores: list[tuple[str, float, list[str]]] = []

        for style_id, spec in styles_cfg.items():
            score = self._score_style(ctx, style_id, spec)
            secondary = self._secondary_tags(ctx, style_id)
            scores.append((style_id, score, secondary))

        scores.sort(key=lambda item: item[1], reverse=True)
        default_style = cfg.get("default_style") or "grid_standard"

        if scores and scores[0][1] >= self.MATCH_THRESHOLD:
            primary, confidence, secondary = scores[0]
        else:
            primary, confidence, secondary = default_style, 0.5, []

        spec = styles_cfg.get(primary, {})
        chain = list(spec.get("parser_chain") or ["grid_standard"])

        return StyleDetectionResult(
            primary_style=primary,
            secondary_styles=secondary,
            confidence=min(confidence, 1.0),
            parser_chain=chain,
            institution_hint=institution_hint,
            institution_authority=institution_authority,
        )

    def _score_style(self, ctx: StyleContext, style_id: str, spec: dict[str, Any]) -> float:
        signals = spec.get("signals") or {}
        headers = self._collect_headers(ctx.tables)
        joined_headers = "".join(headers)

        if ctx.reconstruction and ctx.reconstruction.pipe_header_detected:
            if style_id == "signed_amount":
                return 0.0

        score = 0.0

        required_all = signals.get("header_contains_all") or []
        if required_all:
            if style_id == "compact_merged_ledger":
                if table_has_compact_ledger(ctx.tables):
                    score += 0.35
            else:
                matched = sum(1 for token in required_all if token in joined_headers)
                score += 0.35 * (matched / len(required_all))

        excludes = signals.get("header_excludes_all") or []
        if excludes and all(token not in joined_headers for token in excludes):
            score += 0.1

        any_tokens = signals.get("header_contains_any") or []
        if any_tokens and any(token in joined_headers for token in any_tokens):
            score += 0.2

        excludes_any = signals.get("header_excludes_any") or []
        if excludes_any:
            if any(token in joined_headers for token in excludes_any):
                if style_id == "signed_amount":
                    from docmirror.plugins.bank_statement.header_resolve import has_merged_amount_header

                    if not has_merged_amount_header(ctx.tables):
                        score *= 0.25
                else:
                    score *= 0.25
            else:
                score += 0.1

        if style_id == "split_debit_credit":
            if ctx.reconstruction and ctx.reconstruction.source == "pipe_text":
                score += 0.5
            elif has_split_debit_credit_headers(ctx.tables):
                score += 0.35

        if style_id == "signed_amount":
            from docmirror.plugins.bank_statement.styles.signed_amount import (
                table_has_signed_amount_cells,
            )

            if ctx.reconstruction and ctx.reconstruction.pipe_header_detected:
                return 0.0
            if not table_has_signed_amount_cells(ctx.tables):
                return 0.0
            if ctx.reconstruction and ctx.reconstruction.source not in ("spaced_ocr", "canonical_table", None):
                return 0.0
            score += 0.45

        if style_id == "borderless_ocr":
            from docmirror.plugins.bank_statement.styles.borderless_ocr import (
                is_ocr_dominant,
                table_is_borderless_ocr,
            )

            if not table_is_borderless_ocr(ctx):
                return 0.0
            score += 0.4
            if is_ocr_dominant(ctx):
                score += 0.15

        hints = signals.get("column_hints") or []
        if hints:
            matched = sum(1 for h in hints if any(h in hdr for hdr in headers))
            min_cols = signals.get("min_matched_columns", 3)
            if matched >= min_cols:
                score += 0.25
            elif matched > 0:
                score += 0.1 * (matched / max(min_cols, 1))

        cell_pattern = signals.get("cell_pattern")
        if cell_pattern:
            pattern = re.compile(cell_pattern)
            if self._tables_match_cell_pattern(ctx.tables, pattern):
                score += 0.35

        if style_id == "compact_merged_ledger" and table_has_compact_ledger(ctx.tables):
            score = max(score, 0.85)

        priority = float(spec.get("priority") or 0) / 200.0
        score += priority
        return min(score, 1.0)

    @staticmethod
    def _collect_headers(tables: list[list[list[str]]]) -> list[str]:
        headers: list[str] = []
        for tbl in tables:
            for row in tbl[:12]:
                for cell in row:
                    text = str(cell or "").strip()
                    if text and text not in headers:
                        headers.append(text)
        return headers

    @staticmethod
    def _tables_match_cell_pattern(tables: list[list[list[str]]], pattern: re.Pattern[str]) -> bool:
        for tbl in tables:
            for row in tbl:
                if row and pattern.match(str(row[0] or "").strip()):
                    return True
        return False

    @staticmethod
    def _secondary_tags(ctx: StyleContext, primary: str) -> list[str]:
        tags: list[str] = []
        if ctx.reconstruction and ctx.reconstruction.source == "pipe_text":
            tags.append("pipe_ledger_text")
        if table_has_compact_ledger(ctx.tables):
            if primary != "compact_merged_ledger":
                tags.append("compact_merged_ledger")
            if BankStyleDetector._has_continuation_rows(ctx.tables):
                tags.append("multiline_continuation")
            tags.append("kv_header_table_body")
        return tags

    @staticmethod
    def _has_continuation_rows(tables: list[list[list[str]]]) -> bool:
        for tbl in tables:
            for row in tbl:
                if row and _TIME_ONLY.match(str(row[0] or "").strip()):
                    return True
        return False
