"""
Column registry — declarative header-to-field mapping for table parsers.

Defines ``ColumnMapping`` (standard field name, enum map, format hints, aliases)
and ``ColumnMatcher`` (fuzzy header row matching). Community plugins configure
parsing through a registry dict rather than hard-coded column names.

Pipeline role: ``BaseTableParser`` and bank-statement ``header_resolve`` use
``ColumnMatcher`` during ``extract_from_mirror`` to map Mirror table headers to
canonical transaction fields.

Key exports: ``ColumnMapping``, ``ColumnMatcher``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ColumnMapping:
    """Single column mapping definition.

    :param field: normalized field name (e.g. amount, trade_no)
    :param enum_map: enum value mapping (e.g. {"收入": "income", "支出": "expense"})
    :param unit: unit (e.g. CNY)
    :param format_hint: format hint (e.g. datetime)
    :param aliases: additional column name variants (auto-registered)
    """

    field: str
    enum_map: dict[str, str] | None = None
    unit: str | None = None
    format_hint: str | None = None
    aliases: list[str] | None = None


class ColumnMatcher:
    """Adaptive column matcher: performs fuzzy matching on header rows, returns {standard_field: column_index}.

    Supports:
    - Exact match
    - Substring match ("金额(元)" contains "金额")
    - Match after removing spaces/newlines
    - Registered column name variant matching
    """

    def __init__(self, registry: dict[str, ColumnMapping]):
        self._registry = registry
        # Build variant index: {variant_name: standard_field}
        self._variant_index: dict[str, str] = {}
        for canonical_name, mapping in registry.items():
            # Register canonical name
            clean = self._clean(canonical_name)
            self._variant_index[clean] = mapping.field
            # Register alias
            if mapping.aliases:
                for alias in mapping.aliases:
                    self._variant_index[self._clean(alias)] = mapping.field

    @staticmethod
    def _clean(text: str) -> str:
        """Remove spaces, newlines, fullwidth/halfwidth differences."""
        return re.sub(r"[\s\n\r\t\u3000]", "", text).replace("\u00a0", "")

    def match(self, header_cells: list[str]) -> dict[str, int]:
        """Match columns in header row, return {standard_field: column_index}.

        策略：
        1. 精确匹配（规范名、别名）
        2. 子串包含（如 "金额(元)" → amount）
        3. 无匹配列跳过
        """
        col_map: dict[str, int] = {}
        used_fields: set[str] = set()

        for col_idx, cell in enumerate(header_cells):
            cell_clean = self._clean(cell)
            if not cell_clean:
                continue

            # Strategy 1: exact match against variant index
            if cell_clean in self._variant_index:
                field_name = self._variant_index[cell_clean]
                if field_name not in used_fields:
                    col_map[field_name] = col_idx
                    used_fields.add(field_name)
                continue

            # Strategy 2: substring match
            for canonical_name, mapping in self._registry.items():
                if mapping.field in used_fields:
                    continue
                clean_canon = self._clean(canonical_name)
                if clean_canon in cell_clean or cell_clean in clean_canon:
                    col_map[mapping.field] = col_idx
                    used_fields.add(mapping.field)
                    break

        return col_map

    def match_headers(self, rows: list[list[str]], max_lookahead: int = 8) -> dict[str, int] | None:
        """Scan the first N rows of the table to find the header, return {standard_field: column_index}.

        找到 >= 3 列匹配即认为找到表头。
        返回 None 表示未找到。
        """
        best: dict[str, int] | None = None
        best_count = 0

        for row_idx, row in enumerate(rows[:max_lookahead]):
            col_map = self.match(row)
            count = len(col_map)
            if count >= 3 and count > best_count:
                best = col_map
                best_count = count
            if count >= min(4, len(self._registry)):
                return col_map  # 足够匹配，直接返回

        return best
