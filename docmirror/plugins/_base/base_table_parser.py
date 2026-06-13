"""
BaseTableParser — 通用流水解析器基类
======================================

社区版 table_document 形态的基础解析器。

所有 cashflow_payment 领域的插件（微信流水、支付宝流水、银行流水等）
都应继承此类，仅提供 column_registry、identity_fields、scene_keywords 等配置。
"""

from __future__ import annotations

import logging
import re
from abc import abstractmethod
from collections.abc import Sequence
from typing import Any

from docmirror.plugins import DomainPlugin
from docmirror.plugins._base.column_registry import ColumnMapping, ColumnMatcher
from docmirror.plugins._base.standardizer import (
    extract_period,
    normalize_amount,
    normalize_enum,
    normalize_timestamp,
)

logger = logging.getLogger(__name__)

_ISO_DATE_RE = re.compile(r"^\d{4}[-/]\d{2}[-/]\d{2}")
_ISO_DATETIME_RE = re.compile(r"^\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2}")


class BaseTableParser(DomainPlugin):
    """通用流水解析器基类。

    子类只需实现以下抽象属性：
    - domain_name
    - display_name
    - scene_keywords
    - column_registry (Dict[str, ColumnMapping])
    - standard_fields (List[str])

    可选覆盖：
    - identity_fields
    - edition (默认 community)
    """

    # ── 子类必须实现的抽象属性 ──

    @property
    @abstractmethod
    def column_registry(self) -> dict[str, ColumnMapping]:
        """列映射注册表。"""
        ...

    @property
    @abstractmethod
    def standard_fields(self) -> list[str]:
        """标准化字段顺序（用于 normalized 块）。"""
        ...

    # ── 可选覆盖 ──

    @property
    def identity_fields(self) -> Sequence[tuple[str, Sequence[str]]]:
        return ()

    @property
    def edition(self) -> str:
        return "community"

    # ── Public API ──

    def extract_from_mirror(self, parse_result, text: str = "") -> dict[str, Any]:
        """从 ParseResult 中提取并返回 v2.0 社区版输出。"""
        # Step 1: 提取 KV 头部区
        identity_fields = self._extract_identity(parse_result)

        # Step 2: 提取交易表格
        tables = self._collect_tables(parse_result)

        # Step 3: 检测表头
        header_row_idx, raw_headers, col_map = self._detect_headers(tables)

        # Step 4: 提取交易记录
        transactions = self._extract_records(tables, header_row_idx, raw_headers, col_map)

        # Step 5: 构建 records (raw + normalized)
        records = self._build_records(transactions)

        # Step 6: 汇总统计
        summary = self._build_summary(records)

        # Step 7: 周期
        period = extract_period(text) or summary.get("period", {})

        # Step 8: 构建输出
        return self._build_output(
            parse_result, identity_fields, records, raw_headers, summary, period, text=text,
        )

    # ── Step 1: KV 头部区提取 ──

    def _extract_identity(self, parse_result) -> dict[str, dict]:
        """从 mirror KV pair 中提取身份字段。

        返回 {field_key: {raw_name, raw_value, normalized_value, data_type}}。
        """
        fields: dict[str, dict] = {}
        if not parse_result or not hasattr(parse_result, "pages"):
            return fields

        identity_config = self.identity_fields or ()

        for page in getattr(parse_result, "pages", []):
            for kv in getattr(page, "key_values", []):
                key = kv.key.strip() if hasattr(kv, "key") else ""
                val = kv.value.strip() if hasattr(kv, "value") else ""
                if not key:
                    continue

                for field_name, candidate_keys in identity_config:
                    if field_name in fields:
                        continue  # 已找到
                    for ck in candidate_keys:
                        if ck in key:
                            fields[field_name] = {
                                "raw_name": key,
                                "raw_value": val,
                                "normalized_value": self._normalize_identity(field_name, val),
                                "data_type": "string",
                            }
                            break

                # 通用字段检测（即使 identity_config 为空也尝试）
                if "account_holder" not in fields and "兹证明" in key:
                    name = re.sub(r"\(.*", "", val).strip()
                    if name:
                        fields["account_holder"] = {
                            "raw_name": key,
                            "raw_value": val,
                            "normalized_value": name,
                            "data_type": "string",
                        }
                if "account_number" not in fields and "证件号码" in key:
                    m = re.search(r"(\d{6,})", val)
                    if m:
                        fields["account_number"] = {
                            "raw_name": key,
                            "raw_value": val,
                            "normalized_value": m.group(1),
                            "data_type": "string",
                        }
                if "currency" not in fields and key in ("币种", "Currency"):
                    fields["currency"] = {
                        "raw_name": key,
                        "raw_value": val,
                        "normalized_value": "CNY" if "人民" in val else val,
                        "data_type": "string",
                    }

        return fields

    @staticmethod
    def _normalize_identity(field_name: str, raw_value: str) -> str:
        """对身份字段值进行基础标准化。"""
        if field_name == "currency":
            if "人民" in raw_value:
                return "CNY"
            return raw_value
        return raw_value

    # ── Step 2: 收集表格 ──

    def _collect_tables(self, parse_result) -> list[list[list[str]]]:
        """从 ParseResult 中收集所有表格。

        优先级：
          1. logical_tables（已跨页合并的逻辑表）— 优先使用
          2. physical pages[].tables（每页原始表）— 旧版 fallback

        返回 [[[cell_text, ...], ...], ...] 结构。
        """
        import re

        out: list[list[list[str]]] = []

        if not parse_result or not hasattr(parse_result, "pages"):
            return out

        # Try logical tables first (composed cross-page)
        from docmirror.core.table.table_access import get_logical_tables

        logical = get_logical_tables(parse_result)
        if logical:
            for lt in logical:
                rows: list[list[str]] = []
                # Insert headers as first row
                if lt.headers:
                    rows.append(lt.headers)
                for row in lt.rows:
                    cells = [c.text for c in getattr(row, "cells", [])]
                    if cells:
                        rows.append(cells)
                if rows:
                    out.append(rows)
            return out

        # Fallback: physical per-page tables (legacy)
        for page in getattr(parse_result, "pages", []):
            for table in getattr(page, "tables", []):
                tbl_headers = getattr(table, "headers", []) or []
                rows: list[list[str]] = []
                for row in getattr(table, "rows", []):
                    cells = [c.text for c in getattr(row, "cells", [])]
                    if cells:
                        rows.append(cells)

                if not rows:
                    if tbl_headers:
                        rows.append(tbl_headers)
                elif tbl_headers:
                    # Check if first row is already the header (no date/long-number pattern)
                    first_vals = [c.lower().strip() for c in rows[0][:3] if c.strip()] if rows[0] else []
                    has_date = any(re.match(r"^\d{4}[-/]", v) for v in first_vals)
                    has_digit = any(re.match(r"^\d{16,}", v) for v in first_vals)
                    if not has_date and not has_digit:
                        pass  # First row looks like headers already
                    else:
                        # First row is data — prepend table.headers
                        rows.insert(0, tbl_headers)

                if rows:
                    out.append(rows)
        return out

    # ── Step 3: 表头检测 ──

    def _detect_headers(
        self, tables: list[list[list[str]]],
    ) -> tuple[int, list[str], dict[str, int]]:
        """检测表头行。

        使用 ColumnMatcher 对每张表的前 N 行做列匹配。
        返回 (header_row_index, raw_headers, col_map)。

        col_map: {标准字段名: 列索引}
        """
        matcher = ColumnMatcher(self.column_registry)

        for tbl in tables:
            if not tbl:
                continue
            for row_idx, row in enumerate(tbl[:8]):
                col_map = matcher.match(row)
                if len(col_map) >= 3:
                    return row_idx, [str(c or "").strip() for c in row], col_map

        return 0, [], {}

    # ── Step 4: 提取交易记录 ──

    def _extract_records(
        self,
        tables: list[list[list[str]]],
        header_row_idx: int,
        raw_headers: list[str],
        col_map: dict[str, int],
    ) -> list[dict[str, str]]:
        """从表格中提取交易行。

        处理策略：
        - 跳过表头行
        - 跳过空行
        - 首列为日期/长数字则认为是数据行
        """
        transactions: list[dict[str, str]] = []
        has_col_map = bool(col_map)

        for tbl in tables:
            if not tbl or header_row_idx >= len(tbl):
                continue

            for row in tbl[header_row_idx + 1:]:
                if not row or not any(str(c).strip() for c in row):
                    continue

                # 跳过汇总行（含"合计"、"小计"、"本页"等）
                first_cell = str(row[0] or "").strip() if row else ""
                if any(kw in first_cell for kw in ("合计", "小计", "本页", "总计", "收入", "支出")):
                    continue

                # 首列验证：必须是日期或长数字（交易单号）
                if not _ISO_DATE_RE.match(first_cell) and not re.match(r"^\d{16,}", first_cell):
                    date_cell = next(
                        (str(c).strip() for c in row if _ISO_DATE_RE.match(str(c).strip()) or _ISO_DATETIME_RE.match(str(c).strip())),
                        "",
                    )
                    if not date_cell:
                        continue

                # 使用 col_map 提取
                if has_col_map:
                    txn: dict[str, str] = {}
                    for field_name, col_idx in col_map.items():
                        if col_idx < len(row):
                            txn[raw_headers[col_idx] if col_idx < len(raw_headers) else f"col_{col_idx}"] = str(row[col_idx] or "").strip()
                    if any(txn.values()):
                        transactions.append(txn)
                else:
                    # 无 col_map，按原始列索引
                    txn = {}
                    for i, cell in enumerate(row):
                        h = raw_headers[i] if i < len(raw_headers) else f"col_{i}"
                        txn[h] = str(cell or "").strip()
                    if any(txn.values()):
                        transactions.append(txn)

        return transactions

    # ── Step 5: 构建 records (raw + normalized) ──

    def _build_records(self, transactions: list[dict[str, str]]) -> list[dict]:
        """构建标准 records 格式。

        每条记录包含：
        - row_index: int
        - raw: dict (原始值，key 为表头列名)
        - normalized: dict (标准化值)
        """
        records: list[dict] = []

        for idx, raw_txn in enumerate(transactions, start=1):
            normalized = self._normalize(raw_txn)
            records.append({
                "row_index": idx,
                "raw": dict(raw_txn),
                "normalized": normalized,
            })

        return records

    def _normalize(self, raw_txn: dict[str, str]) -> dict[str, Any]:
        """对单条原始交易进行标准化。

        使用 column_registry 中的映射进行：
        - 枚举转换（方向、类型等）
        - 金额转换 str → float
        - 时间格式化
        - 字段默认值
        """
        normalized: dict[str, Any] = {}

        # 先通过 column_registry 的 canonical_name 建立字段值
        for canonical_name, mapping in self.column_registry.items():
            # 在 raw_txn 中查找匹配的 key
            raw_val = ""
            for raw_key, raw_v in raw_txn.items():
                if raw_key == canonical_name or (mapping.aliases and raw_key in mapping.aliases):
                    raw_val = raw_v
                    break
            if not raw_val:
                # 子串匹配
                for raw_key, raw_v in raw_txn.items():
                    if canonical_name in raw_key or raw_key in canonical_name:
                        raw_val = raw_v
                        break

            if mapping.enum_map:
                normalized[mapping.field] = normalize_enum(raw_val, mapping.enum_map)
            elif mapping.field == "amount":
                normalized[mapping.field] = normalize_amount(raw_val)
                normalized["amount_cny"] = normalized[mapping.field]  # 默认为自身
            elif mapping.field == "timestamp":
                normalized[mapping.field] = normalize_timestamp(raw_val)
            else:
                normalized[mapping.field] = raw_val

        # 确保所有 standard_fields 都有默认值
        for field in self.standard_fields:
            if field not in normalized:
                if field == "amount":
                    normalized[field] = None
                    normalized["amount_cny"] = None
                else:
                    normalized[field] = ""

        return normalized

    # ── Step 6: 汇总统计 ──

    @staticmethod
    def _build_summary(records: list[dict]) -> dict[str, Any]:
        """构建汇总统计。

        包括：
        - total_rows
        - total_income / total_expense / net_flow
        - period (从记录中推断)
        - statistics (count / avg / max)
        """
        income_recs = [r for r in records if r["normalized"].get("direction") == "income"]
        expense_recs = [r for r in records if r["normalized"].get("direction") == "expense"]
        other_recs = [r for r in records if r["normalized"].get("direction") not in ("income", "expense")]

        income_amounts = [
            r["normalized"]["amount"] for r in income_recs
            if r["normalized"].get("amount") is not None
        ]
        expense_amounts = [
            r["normalized"]["amount"] for r in expense_recs
            if r["normalized"].get("amount") is not None
        ]

        total_income = round(sum(income_amounts), 2) if income_amounts else 0.0
        total_expense = round(sum(expense_amounts), 2) if expense_amounts else 0.0

        all_ts = sorted(
            r["normalized"]["timestamp"] for r in records if r["normalized"].get("timestamp")
        )
        period: dict[str, str] = {}
        if len(all_ts) >= 2:
            period = {"start": all_ts[0][:10], "end": all_ts[-1][:10]}
        elif len(all_ts) == 1:
            period = {"start": all_ts[0][:10], "end": all_ts[0][:10]}

        return {
            "total_rows": len(records),
            "total_income": total_income,
            "total_expense": total_expense,
            "net_flow": round(total_income - total_expense, 2),
            "period": period,
            "statistics": {
                "income_count": len(income_recs),
                "expense_count": len(expense_recs),
                "other_count": len(other_recs),
                "avg_income": round(total_income / len(income_recs), 2) if income_recs else 0.0,
                "avg_expense": round(total_expense / len(expense_recs), 2) if expense_recs else 0.0,
                "max_income": round(max(income_amounts), 2) if income_amounts else 0.0,
                "max_expense": round(max(expense_amounts), 2) if expense_amounts else 0.0,
            },
        }

    # ── Step 8: 构建 v2.0 输出 ──

    def _build_output(
        self,
        parse_result,
        identity_fields: dict[str, dict],
        records: list[dict],
        raw_headers: list[str],
        summary: dict[str, Any],
        period: str | dict,
        *,
        text: str = "",
    ) -> dict[str, Any]:
        """Build edition v2.0 via DEC → ``edition_serializer``."""
        from docmirror.plugins._base.table_dec import serialize_table_plugin_output

        return serialize_table_plugin_output(
            self,
            parse_result,
            identity_fields=identity_fields,
            records=records,
            summary=summary,
            text=text,
            domain=self._detect_domain(),
            match_method="keyword_layout_hybrid",
        )

    @staticmethod
    def _detect_domain() -> str:
        """检测业务域。"""
        return "cashflow_payment"
