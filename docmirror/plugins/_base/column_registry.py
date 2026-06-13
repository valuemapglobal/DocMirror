"""
Column Registry — 列映射注册表
=================================

定义 ColumnMapping 数据类和列匹配器。
社区版插件通过 column_registry 配置驱动解析，而非硬编码列名。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ColumnMapping:
    """单列映射定义。

    :param field: 标准化后的字段名（如 amount、trade_no）
    :param enum_map: 枚举值映射（如 {"收入": "income", "支出": "expense"}）
    :param unit: 单位（如 CNY）
    :param format_hint: 格式提示（如 datetime）
    :param aliases: 额外的列名变体（自动注册）
    """

    field: str
    enum_map: dict[str, str] | None = None
    unit: str | None = None
    format_hint: str | None = None
    aliases: list[str] | None = None


class ColumnMatcher:
    """自适应列匹配器：对表头行进行模糊匹配，返回 {标准字段名: 列索引}。

    支持：
    - 精确匹配
    - 子串匹配（"金额(元)" 包含 "金额"）
    - 去除空格/换行后的匹配
    - 注册的列名变体匹配
    """

    def __init__(self, registry: dict[str, ColumnMapping]):
        self._registry = registry
        # 构建变体索引：{ 变体名: 标准字段名 }
        self._variant_index: dict[str, str] = {}
        for canonical_name, mapping in registry.items():
            # 注册规范名
            clean = self._clean(canonical_name)
            self._variant_index[clean] = mapping.field
            # 注册别名
            if mapping.aliases:
                for alias in mapping.aliases:
                    self._variant_index[self._clean(alias)] = mapping.field

    @staticmethod
    def _clean(text: str) -> str:
        """去除空格、换行、全角半角差异。"""
        return re.sub(r"[\s\n\r\t\u3000]", "", text).replace("\u00a0", "")

    def match(self, header_cells: list[str]) -> dict[str, int]:
        """对表头行逐列匹配，返回 {标准字段名: 列索引}。

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

            # 策略1：精确匹配变体索引
            if cell_clean in self._variant_index:
                field_name = self._variant_index[cell_clean]
                if field_name not in used_fields:
                    col_map[field_name] = col_idx
                    used_fields.add(field_name)
                continue

            # 策略2：子串匹配
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
        """遍历表的前 N 行查找表头，返回 {标准字段名: 列索引}。

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
