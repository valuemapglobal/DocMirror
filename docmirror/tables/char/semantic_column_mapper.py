# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Semantic Column Mapper — tokenize and assign row values by semantic type.

Core insight: column headers are the most reliable signal for column
structure.  Positional analysis (x-coordinates) is a noisy proxy that
fails when PDF text objects merge adjacent column values.

This mapper classifies column types from headers, tokenizes data rows
by semantic patterns (date, amount, account), then assigns tokens to
the best-matching column — without relying on x-position gaps.

Main entry: ``SemanticColumnMapper.map_row()``

Integration: called by the table structure stage as a conservative repair
for fused values that x-coordinate heuristics cannot separate.
"""

from __future__ import annotations

import re
from typing import Any


class SemanticColumnMapper:
    """Tokenize fused row values and assign to semantically typed columns."""

    # ── Semantic type patterns ──
    DATE_PATTERN = re.compile(r"\d{4}[-/]\d{2}[-/]\d{2}")
    AMOUNT_PATTERN = re.compile(r"(?:[\d,]+\.\d{2})")
    ACCOUNT_PATTERN = re.compile(r"\d{10,20}")
    CURRENCY_PATTERN = re.compile(r"[\d,]+\.\d{2}")

    # ── Column header → type mapping ──
    # Each entry: (keyword list, type label)
    HEADER_RULES: list[tuple[list[str], str]] = [
        # 日期/日期型列
        (["date", "posting", "value", "交易日期", "起息日", "过账日", "日期", "时间"], "date"),
        # 金额/借方/贷方/余额
        (["debit", "借方", "支出", "支付", "借"], "debit"),
        (["credit", "贷方", "收入", "入账", "deposit", "贷"], "credit"),
        (["balance", "余额", "bal", "剩余"], "balance"),
        (["amount", "金额", "发生额", "sum", "总额"], "amount"),
        # 摘要/描述
        (["摘要", "description", "备注", "remark", "note", "detail", "过账内容", "交易内容", "产品"], "text"),
        # 账号/户名
        (["account", "账号", "户名", "name", "counterparty", "对方户名", "对方账户"], "account"),
        # 渠道/编号
        (["channel", "渠道", "id", "编号", "序号", "code", "code"], "code"),
    ]

    def __init__(self) -> None:
        self._header_types: list[str] = []

    # ── Public API ──

    def map_table(
        self, table: list[list[str]], headers: list[str] | None = None
    ) -> list[list[str]] | None:
        """Map an entire table using semantic column analysis.

        If ``headers`` is provided, it overrides extracting headers from
        the first row of ``table``.
        """
        if not table or len(table) < 2:
            return None

        use_headers = headers or table[0]
        column_types = self.classify_columns(use_headers)
        modified = False

        result: list[list[str]] = [list(row) for row in table]
        start_idx = 1 if not headers else 0

        for row_idx in range(start_idx, len(result)):
            row = result[row_idx]
            new_row = self.map_row(row, column_types)
            if new_row and new_row != row:
                result[row_idx] = new_row
                modified = True

        return result if modified else None

    def map_row(self, row: list[str], column_types: list[str]) -> list[str]:
        """Map a single fused row to columns using semantic matching."""
        if not row or not column_types or len(row) != len(column_types):
            return row

        if not self._looks_fused(row):
            return row

        fused = " ".join(c.strip() for c in row)
        tokens = self.tokenize_row(fused)
        if len(tokens) < 2:
            return row  # no structured content to redistribute

        assigned = self.assign_to_columns(tokens, column_types)
        return assigned

    # ── Step 1: Classify column types from headers ──

    def classify_columns(self, headers: list[str]) -> list[str]:
        """Infer column types from header text.

        Returns a list of type labels (``"date"``, ``"debit"``,
        ``"credit"``, ``"balance"``, ``"amount"``, ``"text"``,
        ``"account"``, ``"code"``).
        """
        if not headers:
            return []

        types: list[str] = []
        for header in headers:
            h = header.lower().strip()
            matched = "text"
            best_len = 0

            for keywords, col_type in self.HEADER_RULES:
                for kw in keywords:
                    if kw in h:
                        # prefer more specific keywords (longer = more specific)
                        if len(kw) > best_len:
                            best_len = len(kw)
                            matched = col_type

            types.append(matched)

        self._header_types = types
        return types

    # ── Step 2: Tokenize fused text ──

    def tokenize_row(self, fused_text: str) -> list[tuple[str, str]]:
        """Split fused row content into (value, type) tokens.

        Tokenization is greedy — it scans left-to-right, matching the
        most constrained pattern (date) first, then amount, then account,
        and the remainder is text.
        """
        tokens: list[tuple[str, str]] = []
        remaining = fused_text.strip()

        while remaining:
            pos = len(remaining)
            match_val = ""
            match_type = "text"

            # Try date (most constrained)
            m = self.DATE_PATTERN.search(remaining)
            if m and m.start() < pos:
                pos, match_val, match_type = m.start(), m.group(), "date"

            # Try amount (second most constrained)
            m = self.AMOUNT_PATTERN.search(remaining)
            if m and m.start() < pos:
                pos, match_val, match_type = m.start(), m.group(), "amount"

            # Try account number
            m = self.ACCOUNT_PATTERN.search(remaining)
            if m and m.start() < pos:
                pos, match_val, match_type = m.start(), m.group(), "account"

            if pos > 0 and match_val:
                # Text before the matched value
                prefix = remaining[:pos].strip()
                if prefix:
                    tokens.append((prefix, "text"))
                tokens.append((match_val, match_type))
                remaining = remaining[pos + len(match_val):]
            elif match_val:
                tokens.append((match_val, match_type))
                remaining = remaining[len(match_val):]
            else:
                # No structured value found — rest is text
                # Check if there's residual text after the last match
                if remaining.strip():
                    tokens.append((remaining.strip(), "text"))
                break

        return tokens

    def tokenize(self, fused_text: str) -> list[tuple[str, str]]:
        """Backward-compatible alias for ``tokenize_row``."""
        return self.tokenize_row(fused_text)

    # ── Step 3: Assign tokens to columns ──

    def assign_to_columns(
        self, tokens: list[tuple[str, str]], column_types: list[str]
    ) -> list[str]:
        """Assign tokens to the best-matching columns.

        Strategy:
        1. Group tokens by their semantic type.
        2. For each column, collect all tokens of the matching type.
        3. Assign the collected tokens to the column.

        For text tokens, distribute evenly across remaining spaces.
        """
        cells: list[str] = ["" for _ in column_types]
        used_token_indexes: set[int] = set()
        _AMOUNT_LIKE = {"debit", "credit", "balance", "amount"}

        def _type_match(ct, vt):
            return ct == vt or (vt == "amount" and ct in _AMOUNT_LIKE)

        # Phase A: Assign structured tokens to matching columns
        for token_idx, (value, value_type) in enumerate(tokens):
            if value_type == "text":
                continue
            for ci, col_type in enumerate(column_types):
                if cells[ci]:
                    continue
                if _type_match(col_type, value_type):
                    cells[ci] = value
                    used_token_indexes.add(token_idx)
                    break

        # Phase A2: Remaining structured tokens → first text column
        for token_idx, (value, value_type) in enumerate(tokens):
            if value_type == "text" or token_idx in used_token_indexes:
                continue
            for ci, col_type in enumerate(column_types):
                if cells[ci]:
                    continue
                if col_type == "text":
                    cells[ci] = value
                    used_token_indexes.add(token_idx)
                    break

        # Phase B: Distribute text tokens to empty columns
        text_tokens = [
            (token_idx, value)
            for token_idx, (value, value_type) in enumerate(tokens)
            if value_type == "text" and token_idx not in used_token_indexes
        ]
        for token_idx, value in text_tokens:
            for ci in range(len(column_types)):
                if not cells[ci].strip():
                    cells[ci] = value
                    used_token_indexes.add(token_idx)
                    break
            else:
                # All columns filled — append to last column
                if cells:
                    cells[-1] += f" {value}"

        # Phase C: Fill any still-empty columns from remaining text
        # (If we have columns that no token matched, fill from text tokens)
        for ci in range(len(column_types)):
            if not cells[ci].strip():
                for value, _ in tokens:
                    if value not in cells:
                        cells[ci] = value
                        break

        return [c.strip() for c in cells]

    def _assign(
        self, tokens: list[tuple[str, str]], column_types: list[str]
    ) -> list[str]:
        """Backward-compatible alias for ``assign_to_columns``."""
        return self.assign_to_columns(tokens, column_types)

    # ── Helpers ──

    def get_header_types(self) -> list[str]:
        return self._header_types

    def _looks_fused(self, row: list[str]) -> bool:
        """Return true only when a row has evidence of merged semantic values."""
        non_empty = [str(cell or "").strip() for cell in row if str(cell or "").strip()]
        if len(non_empty) < len(row):
            return True

        for cell in non_empty:
            tokens = self.tokenize_row(cell)
            structured_count = sum(1 for _, token_type in tokens if token_type != "text")
            if structured_count >= 2:
                return True
        return False
