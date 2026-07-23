# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Bank statement style parser registry and fallback orchestration.

Maps detected style IDs to parser modules under ``bank_statement.styles``,
runs the primary parser chain, scores record completeness with CAPS coverage,
and falls back to ``grid_standard`` / ``borderless_ocr`` when primary is sparse.

Pipeline role: core dispatch layer between ``BankStyleDetector`` and canonical
record builders inside ``community_plugin.recognize``.

Key exports: ``BankStyleParserRegistry``.

Dependencies: ``bank_statement.styles.*``, ``bank_statement.canonical``.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

from docmirror.plugins.bank_statement.canonical import ensure_canonical_normalized, records_from_raw_transactions
from docmirror.plugins.bank_statement.context import StyleContext
from docmirror.plugins.bank_statement.evidence_atom_table_recovery import recover_evidence_atom_bank_tables
from docmirror.plugins.bank_statement.ocr_implicit_table_recovery import (
    recover_ocr_implicit_ledger_tables,
    recovered_ocr_implicit_row_count,
)
from docmirror.plugins.bank_statement.style_detector import StyleDetectionResult
from docmirror.plugins.bank_statement.styles import (
    borderless_ocr,
    compact_merged,
    grid_standard,
    kv_identity,
    signed_amount,
)
from docmirror.plugins.bank_statement.text_table_builder import build_tables_from_stacked_bank_text
from docmirror.plugins.bank_statement.wide_table_recovery import (
    count_expected_rows_from_bank_footer,
    recover_wide_bank_tables,
)

logger = logging.getLogger(__name__)

_PARSERS = {
    "compact_merged": compact_merged,
    "grid_standard": grid_standard,
    "kv_identity": kv_identity,
    "signed_amount": signed_amount,
    "borderless_ocr": borderless_ocr,
}

_FALLBACK_PARSER_IDS = ("grid_standard", "borderless_ocr", "signed_amount", "compact_merged")
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


def _batch_raw_width(transactions: list[dict[str, str]], sample: int = 8) -> float:
    """Average number of populated source columns, used only as a tie-breaker."""
    if not transactions:
        return 0.0
    widths = [
        sum(bool(str(value or "").strip()) for key, value in transaction.items() if not key.startswith("_"))
        for transaction in transactions[:sample]
    ]
    return sum(widths) / len(widths)


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
    footer_expected = count_expected_rows_from_bank_footer(ctx.full_text)
    if footer_expected > 0:
        return footer_expected
    ocr_expected = recovered_ocr_implicit_row_count(ctx.parse_result)
    if ocr_expected > 0:
        return ocr_expected
    if ctx.parse_result is not None:
        from docmirror.evidence.spe_consumer import mirror_expected_primary_rows, read_structure_spe

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

        if not transactions:
            stacked_tables = _solve_split_debit_credit_tables(ctx.full_text) or build_tables_from_stacked_bank_text(
                ctx.full_text
            )
            if stacked_tables:
                stacked_ctx = replace(ctx, tables=stacked_tables)
                transactions = grid_standard.extract_transactions(stacked_ctx, plugin)
                if transactions:

                    def _stacked_normalize(raw):
                        return grid_standard.normalize_record(raw, plugin)

                    normalize_fn = _stacked_normalize
                    if ctx.reconstruction is not None:
                        ctx.reconstruction = replace(
                            ctx.reconstruction,
                            source="stacked_text",
                            expected_primary_rows=len(transactions),
                            pipe_parse_failed=False,
                        )
                    logger.info(
                        "[BankStyleRegistry] stacked text fallback rows=%d",
                        len(transactions),
                    )

        expected = _expected_rows(ctx)
        primary_parser = (detection.parser_chain or ["grid_standard"])[-1]
        primary_score, coverage = _parser_score(transactions, normalize_fn, plugin, expected)
        atom_tables = recover_evidence_atom_bank_tables(ctx.parse_result)
        if atom_tables:
            atom_count = sum(max(len(table) - 1, 0) for table in atom_tables)
            atom_expected = max(expected, atom_count)
            atom_ctx = replace(ctx, tables=atom_tables)
            atom_batch, atom_norm = _run_parser("grid_standard", atom_ctx, plugin)
            atom_score, atom_coverage = _parser_score(atom_batch, atom_norm, plugin, atom_expected)
            richer_equal_coverage = (
                len(atom_batch) >= len(transactions)
                and atom_coverage >= coverage
                and _batch_raw_width(atom_batch) > _batch_raw_width(transactions) + 1.0
            )
            if atom_score > primary_score or richer_equal_coverage:
                transactions = atom_batch
                normalize_fn = atom_norm
                primary_score = atom_score
                coverage = atom_coverage
                expected = atom_expected
                if ctx.reconstruction is not None:
                    ctx.reconstruction = replace(
                        ctx.reconstruction,
                        source="canonical_evidence_table",
                        expected_primary_rows=atom_expected,
                        pipe_parse_failed=False,
                    )
                logger.info(
                    "[BankStyleRegistry] canonical evidence table recovery rows=%d score=%.2f",
                    len(atom_batch),
                    atom_score,
                )
        if primary_score < _CAPS_THRESHOLD or (expected > 0 and coverage < _COVERAGE_THRESHOLD):
            wide_tables = recover_wide_bank_tables(ctx.parse_result, ctx.full_text)
            if wide_tables:
                wide_ctx = replace(ctx, tables=wide_tables)
                wide_batch, wide_norm = _run_parser("grid_standard", wide_ctx, plugin)
                wide_score, wide_coverage = _parser_score(wide_batch, wide_norm, plugin, expected)
                if wide_score > primary_score:
                    transactions = wide_batch
                    normalize_fn = wide_norm
                    primary_score = wide_score
                    coverage = wide_coverage
                    if ctx.reconstruction is not None:
                        ctx.reconstruction = replace(
                            ctx.reconstruction,
                            source="native_wide_table",
                            expected_primary_rows=expected or len(wide_batch),
                            pipe_parse_failed=False,
                        )
                    logger.info(
                        "[BankStyleRegistry] native wide table recovery rows=%d score=%.2f",
                        len(wide_batch),
                        wide_score,
                    )
        primary_score, coverage = _parser_score(transactions, normalize_fn, plugin, expected)
        if primary_score < _CAPS_THRESHOLD or (expected > 0 and coverage < _COVERAGE_THRESHOLD):
            ocr_tables = recover_ocr_implicit_ledger_tables(ctx.parse_result, ctx.full_text)
            if ocr_tables:
                recovered_count = sum(max(len(table) - 1, 0) for table in ocr_tables)
                ocr_expected = max(expected, recovered_count)
                ocr_ctx = replace(ctx, tables=ocr_tables)
                ocr_batch, ocr_norm = _run_parser("grid_standard", ocr_ctx, plugin)
                ocr_score, ocr_coverage = _parser_score(ocr_batch, ocr_norm, plugin, ocr_expected)
                if ocr_score > primary_score:
                    transactions = ocr_batch
                    normalize_fn = ocr_norm
                    primary_score = ocr_score
                    coverage = ocr_coverage
                    expected = ocr_expected
                    if ctx.reconstruction is not None:
                        ctx.reconstruction = replace(
                            ctx.reconstruction,
                            source="ocr_implicit_table",
                            expected_primary_rows=expected or len(ocr_batch),
                            pipe_parse_failed=False,
                        )
                    logger.info(
                        "[BankStyleRegistry] OCR implicit table recovery rows=%d score=%.2f",
                        len(ocr_batch),
                        ocr_score,
                    )
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


def _solve_split_debit_credit_tables(full_text: str) -> list[list[list[str]]]:
    """Use vNext domain solver when debit/credit ledger invariants close."""
    try:
        from docmirror.plugins.bank_statement.semantic_solver import BankStatementSemanticSolver

        solution = BankStatementSemanticSolver().solve(full_text=full_text)
    except Exception as exc:
        logger.debug("[BankStyleRegistry] bank semantic solver skipped: %s", exc)
        return []
    if not solution.success:
        return []
    split_table = (solution.canonical_model or {}).get("split_table")
    if not split_table:
        return []
    logger.info(
        "[BankStyleRegistry] semantic ledger solver rows=%d",
        max(len(split_table) - 1, 0),
    )
    return [split_table]
