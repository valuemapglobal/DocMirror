# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Bank statement style parser registry and fallback orchestration.

Maps detected style IDs to parser modules under ``bank_statement.styles``,
runs the primary parser chain, scores record completeness with CAPS coverage,
and falls back to ``grid_standard`` / ``borderless_ocr`` when primary is sparse.

Pipeline role: core dispatch layer between ``BankStyleDetector`` and canonical
record builders inside ``community_plugin.extract_from_mirror``.

Key exports: ``BankStyleParserRegistry``.

Dependencies: ``bank_statement.styles.*``, ``bank_statement.canonical``.
"""

from __future__ import annotations

import logging
from typing import Any

from docmirror.plugins.bank_statement.canonical import ensure_canonical_normalized, records_from_raw_transactions
from docmirror.plugins.bank_statement.context import StyleContext
from docmirror.plugins.bank_statement.style_detector import StyleDetectionResult
from docmirror.plugins.bank_statement.styles import (
    borderless_ocr,
    compact_merged,
    grid_standard,
    kv_identity,
    signed_amount,
)

logger = logging.getLogger(__name__)

_PARSERS = {
    "compact_merged": compact_merged,
    "grid_standard": grid_standard,
    "kv_identity": kv_identity,
    "signed_amount": signed_amount,
    "borderless_ocr": borderless_ocr,
}

_FALLBACK_PARSER_IDS = ("grid_standard", "borderless_ocr")
_CAPS_THRESHOLD = 0.55
_COVERAGE_THRESHOLD = 0.80


def _field_completeness(records: list[dict[str, Any]], sample: int = 8) -> float:
    if not records:
        return 0.0
    fields = ("date", "amount", "balance")
    scores = []
    for rec in records[:sample]:
        norm = rec.get("normalized") or {}
        scores.append(sum(1 for f in fields if norm.get(f) not in (None, "", 0)) / len(fields))
    return sum(scores) / len(scores)


def _batch_field_completeness(
    transactions: list[dict[str, str]],
    normalize_fn: Any,
    plugin: Any,
) -> float:
    if not transactions:
        return 0.0
    nf = normalize_fn or plugin._normalize
    fields = ("date", "amount", "balance")
    scores = []
    for txn in transactions[:8]:
        norm = ensure_canonical_normalized(nf(txn), plugin.standard_fields)
        scores.append(sum(1 for f in fields if norm.get(f) not in (None, "", 0)) / len(fields))
    return sum(scores) / len(scores)


def _parser_score(
    transactions: list[dict[str, str]],
    normalize_fn: Any,
    plugin: Any,
    expected_rows: int,
) -> tuple[float, float]:
    if not transactions:
        return 0.0, 0.0
    expected = max(expected_rows, 1)
    coverage = min(len(transactions) / expected, 1.0)
    completeness = _batch_field_completeness(transactions, normalize_fn, plugin)
    score = 0.6 * coverage + 0.4 * completeness
    return score, coverage


def _expected_rows(ctx: StyleContext) -> int:
    if ctx.parse_result is not None:
        from docmirror.core.analyze.spe_consumer import mirror_expected_primary_rows, read_structure_spe

        expected = mirror_expected_primary_rows(ctx.parse_result, read_structure_spe(ctx.parse_result))
        if expected > 0:
            return expected
    if ctx.reconstruction and ctx.reconstruction.expected_primary_rows > 0:
        return ctx.reconstruction.expected_primary_rows
    return 0


def _run_parser(parser_id: str, ctx: StyleContext, plugin: Any) -> tuple[list[dict[str, str]], Any]:
    if parser_id == "compact_merged":
        batch = compact_merged.extract_transactions(ctx.tables)
        if batch:
            return batch, compact_merged.normalize_record
    if parser_id == "grid_standard":
        batch = grid_standard.extract_transactions(ctx, plugin)
        return batch, lambda raw: grid_standard.normalize_record(raw, plugin)
    if parser_id == "signed_amount":
        batch = signed_amount.extract_transactions(ctx, plugin)
        return batch, lambda raw: signed_amount.normalize_record(raw, plugin)
    if parser_id == "borderless_ocr":
        batch = borderless_ocr.extract_transactions(ctx, plugin)
        return batch, lambda raw: borderless_ocr.normalize_record(raw, plugin)
    return [], None


class BankStyleParserRegistry:
    """Execute parser_chain and produce v2.0 records."""

    def run(
        self,
        detection: StyleDetectionResult,
        ctx: StyleContext,
        plugin: Any,
    ) -> tuple[list[dict[str, Any]], dict[str, dict]]:
        return self.run_parser_chain(detection, ctx, plugin)

    def run_parser_chain(
        self,
        detection: StyleDetectionResult,
        ctx: StyleContext,
        plugin: Any,
    ) -> tuple[list[dict[str, Any]], dict[str, dict]]:
        identity_fields = plugin._extract_identity(ctx.parse_result)
        transactions: list[dict[str, str]] = []
        normalize_fn = None

        for parser_id in detection.parser_chain:
            module = _PARSERS.get(parser_id)
            if module is None:
                logger.warning("[BankStyleRegistry] unknown parser: %s", parser_id)
                continue

            if parser_id == "kv_identity":
                identity_fields = kv_identity.enrich_identity_fields(
                    ctx,
                    identity_fields,
                    plugin.identity_fields,
                )
                continue

            batch, norm = _run_parser(parser_id, ctx, plugin)
            if batch:
                transactions = batch
                normalize_fn = norm
                continue

        if not transactions and detection.primary_style == "compact_merged_ledger":
            transactions = compact_merged.extract_transactions(ctx.tables)
            normalize_fn = compact_merged.normalize_record

        expected = _expected_rows(ctx)
        primary_parser = (detection.parser_chain or ["grid_standard"])[-1]
        primary_score, coverage = _parser_score(transactions, normalize_fn, plugin, expected)
        needs_fallback = primary_score < _CAPS_THRESHOLD or (expected > 0 and coverage < _COVERAGE_THRESHOLD)
        if needs_fallback:
            best_batch = transactions
            best_norm = normalize_fn
            best_score = primary_score
            for fallback_id in _FALLBACK_PARSER_IDS:
                if fallback_id == primary_parser:
                    continue
                batch, norm = _run_parser(fallback_id, ctx, plugin)
                score, _ = _parser_score(batch, norm, plugin, expected)
                if score > best_score:
                    logger.info(
                        "[BankStyleRegistry] CAPS fallback parser=%s score=%.2f (was %.2f, %d rows)",
                        fallback_id,
                        score,
                        best_score,
                        len(best_batch),
                    )
                    best_batch = batch
                    best_norm = norm
                    best_score = score
            transactions = best_batch
            normalize_fn = best_norm

        if not transactions:
            batch, norm = _run_parser("grid_standard", ctx, plugin)
            transactions = batch
            if norm is None:

                def _grid_normalize(raw):
                    return grid_standard.normalize_record(raw, plugin)

                normalize_fn = _grid_normalize
            else:
                normalize_fn = norm

        if normalize_fn is None:

            def _plugin_normalize(raw):
                return plugin._normalize(raw)

            normalize_fn = _plugin_normalize

        def _normalize(raw: dict[str, str]) -> dict[str, Any]:
            normalized = normalize_fn(raw)
            return ensure_canonical_normalized(normalized, plugin.standard_fields)

        records = records_from_raw_transactions(
            transactions,
            normalize_fn=_normalize,
            style_id=detection.primary_style,
        )

        if "compact_merged" in detection.parser_chain or detection.primary_style == "compact_merged_ledger":
            compact_merged.refine_directions_from_balance_chain(records)

        logger.info(
            "[BankStyleRegistry] style=%s chain=%s records=%d expected=%d",
            detection.primary_style,
            detection.parser_chain,
            len(records),
            expected,
        )
        return records, identity_fields
