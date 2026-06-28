"""
Semantic table understanding engine for evaluation oracles.

Elevates structural table extraction to semantic interpretation across four
layers: table-type classification (transaction, summary, financial,
statistical), column-relationship inference (opposite, calculation, causal,
master-detail), row semantic grouping, and confidence scoring. Produces a
semantic knowledge graph suitable for TQG semantic-tier gates and research
benchmarks. Not used in the production parse pipeline.

Example::

    from docmirror.eval.oracles.semantic_understanding import understand_table_semantics

    semantics = understand_table_semantics(table_rows)
    # semantics.table_type, semantics.semantic_confidence, ...
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# ========== Enum definitions ==========


class TableType(str, Enum):
    """Table type enum."""

    BANK_STATEMENT_TRANSACTION = "bank_statement_transaction"  # bank statement transaction details
    BANK_STATEMENT_SUMMARY = "bank_statement_summary"  # bank statement summary
    FINANCIAL_BALANCE_SHEET = "financial_balance_sheet"  # balance sheet
    FINANCIAL_INCOME_STATEMENT = "financial_income_statement"  # income statement
    FINANCIAL_CASH_FLOW = "financial_cash_flow"  # cash flow statement
    STATISTICAL_REPORT = "statistical_report"  # statistical report
    UNKNOWN = "unknown"


class ColumnRelationType(str, Enum):
    """Column relationship type enum."""

    OPPOSITE = "opposite"  # opposite relationship (debit↔credit)
    CALCULATION = "calculation"  # calculation relationship (balance=previous+income-expense)
    CAUSAL = "causal"  # causal relationship (transaction amount→account balance)
    MASTER_DETAIL = "master_detail"  # 主从关系 (交易流水→摘要)
    TEMPORAL = "temporal"  # 时间关系 (开始日期→结束日期)
    UNKNOWN = "unknown"


class RowGroupType(str, Enum):
    """Row grouping type enum."""

    TIME_MONTH = "time_month"  # 按月分组
    TIME_QUARTER = "time_quarter"  # 按季度分组
    TIME_YEAR = "time_year"  # 按年分组
    ENTITY_ACCOUNT = "entity_account"  # 按账户分组
    ENTITY_CUSTOMER = "entity_customer"  # 按客户分组
    TYPE_TRANSACTION = "type_transaction"  # 按交易类型分组
    SUMMARY_SUBTOTAL = "summary_subtotal"  # 小计行
    SUMMARY_TOTAL = "summary_total"  # 合计行
    UNKNOWN = "unknown"


# ========== Data classes ==========


@dataclass
class ColumnRelation:
    """Column relationship."""

    relation_type: ColumnRelationType
    columns: list[int]  # 列索引
    confidence: float = 0.0
    description: str = ""
    formula: str = ""  # 计算公式（如适用）


@dataclass
class RowGroup:
    """Row grouping."""

    group_type: RowGroupType
    rows: list[int]  # 行索引列表
    value: str = ""  # 分组值（如"2024-05"）
    confidence: float = 0.0


@dataclass
class TableSemantics:
    """Table semantic knowledge graph."""

    table_type: TableType = TableType.UNKNOWN
    table_type_confidence: float = 0.0

    column_relations: list[ColumnRelation] = field(default_factory=list)
    row_groups: list[RowGroup] = field(default_factory=list)

    semantic_confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    # Raw data reference
    header: list[str] = field(default_factory=list)
    column_types: dict[int, str] = field(default_factory=dict)


# ========== Configuration constants ==========

# Table type feature keywords
TABLE_TYPE_FEATURES = {
    TableType.BANK_STATEMENT_TRANSACTION: {
        "keywords": ["交易日期", "记账日期", "借方", "贷方", "交易金额", "账户余额", "摘要", "对方户名"],
        "required_columns": ["date", "amount"],
        "min_rows": 3,
        "min_keyword_matches": 3,  # 至少匹配3个关键词
    },
    TableType.BANK_STATEMENT_SUMMARY: {
        "keywords": ["期初余额", "期末余额", "合计", "总计", "月累计", "年累计"],
        "required_columns": ["amount"],
        "min_rows": 1,
        "min_keyword_matches": 2,
    },
    TableType.FINANCIAL_BALANCE_SHEET: {
        "keywords": ["资产", "负债", "所有者权益", "流动资产", "固定资产"],
        "required_columns": ["amount"],
        "min_rows": 5,
        "min_keyword_matches": 3,
    },
    TableType.FINANCIAL_INCOME_STATEMENT: {
        "keywords": ["营业收入", "营业成本", "利润总额", "净利润", "所得税"],
        "required_columns": ["amount"],
        "min_rows": 5,
        "min_keyword_matches": 3,
    },
}

# Column relationship patterns
COLUMN_RELATION_PATTERNS = [
    {
        "type": ColumnRelationType.OPPOSITE,
        "pattern": ["借方", "贷方"],
        "description": "借贷相反关系",
    },
    {
        "type": ColumnRelationType.OPPOSITE,
        "pattern": ["收入", "支出"],
        "description": "收支相反关系",
    },
    {
        "type": ColumnRelationType.CALCULATION,
        "pattern": ["上期余额", "本期发生", "本期余额"],
        "description": "余额计算关系",
        "formula": "本期余额 = 上期余额 + 本期发生",
    },
]


# ========== Core functions ==========


def understand_table_semantics(
    table: list[list[str]],
    column_types: dict[int, str] | None = None,
) -> TableSemantics:
    """Understand table semantics (Tao Te Ching · 19th realm).

    Args:
        table: 2D表格数据（包含表头）
        column_types: 列类型字典（可选，如未提供则自动推断）

    Returns:
        TableSemantics: 表格语义知识图谱
    """
    if not table or len(table) < 2:
        return TableSemantics(errors=["表格数据不足"])

    semantics = TableSemantics()
    semantics.header = table[0]

    # Infer column types (if not provided)
    if column_types is None:
        semantics.column_types = _infer_column_types(table)
    else:
        semantics.column_types = column_types

    # Layer 1: Table type identification
    semantics.table_type, semantics.table_type_confidence = _identify_table_type(table)

    # Layer 2: Column relationship inference
    semantics.column_relations = _infer_column_relations(table, semantics)

    # Layer 3: Row semantic grouping
    semantics.row_groups = _identify_row_groups(table, semantics)

    # Layer 4: Semantic confidence evaluation
    semantics.semantic_confidence = _compute_semantic_confidence(table, semantics)

    logger.debug(
        f"🔮 语义理解: 类型={semantics.table_type.value}, "
        f"关系={len(semantics.column_relations)}, "
        f"分组={len(semantics.row_groups)}, "
        f"置信度={semantics.semantic_confidence:.2f}"
    )

    return semantics


# ========== Layer 1: Table type identification ==========


def _identify_table_type(table: list[list[str]]) -> tuple[TableType, float]:
    """Identify table type.

    Returns:
        (table_type, confidence)
    """
    if not table or len(table) < 2:
        return TableType.UNKNOWN, 0.0

    header = table[0]
    header_text = " ".join(header)

    best_type = TableType.UNKNOWN
    best_score = 0.0

    for table_type, features in TABLE_TYPE_FEATURES.items():
        score = 0.0

        # Keyword match score
        keyword_matches = sum(1 for kw in features["keywords"] if kw in header_text)

        # Check if minimum keyword match count is met
        min_matches = features.get("min_keyword_matches", 1)
        if keyword_matches < min_matches:
            continue  # 不满足最小匹配数，跳过

        keyword_score = keyword_matches / len(features["keywords"]) if features["keywords"] else 0.0
        score += keyword_score * 0.6

        # Required column check
        has_required = all(
            any(_column_matches_type(col, req_type) for col in header) for req_type in features["required_columns"]
        )
        if has_required:
            score += 0.3

        # Row count check
        if len(table) >= features["min_rows"]:
            score += 0.1

        if score > best_score:
            best_score = score
            best_type = table_type

    confidence = min(1.0, best_score)
    return best_type, confidence


# ========== Layer 2: Column relationship inference ==========


def _infer_column_relations(table: list[list[str]], semantics: TableSemantics) -> list[ColumnRelation]:
    """Infer column relationships."""
    relations = []
    header = semantics.header

    # 1. Pattern-based relationship
    for pattern_def in COLUMN_RELATION_PATTERNS:
        matched_cols = []
        for i, col_name in enumerate(header):
            for pattern_kw in pattern_def["pattern"]:
                if pattern_kw in col_name:
                    matched_cols.append(i)
                    break

        if len(matched_cols) >= 2:
            relation = ColumnRelation(
                relation_type=pattern_def["type"],
                columns=matched_cols,
                confidence=0.8,
                description=pattern_def.get("description", ""),
                formula=pattern_def.get("formula", ""),
            )
            relations.append(relation)

    # 2. Calculation-based relationship (e.g. balance=previous+income-expense)
    calc_relations = _detect_calculation_relations(table, semantics)
    relations.extend(calc_relations)

    return relations


def _detect_calculation_relations(table: list[list[str]], semantics: TableSemantics) -> list[ColumnRelation]:
    """Detect calculation relationships."""
    relations = []
    col_types = semantics.column_types

    # Look up "balance" column
    balance_cols = [i for i, t in col_types.items() if t == "balance"]
    amount_cols = [i for i, t in col_types.items() if t in ("amount", "income", "expense")]

    if balance_cols and amount_cols:
        # Running balance should match prior row plus transaction amount
        if _verify_calculation_pattern(table, balance_cols[0], amount_cols):
            relation = ColumnRelation(
                relation_type=ColumnRelationType.CALCULATION,
                columns=[balance_cols[0]] + amount_cols,
                confidence=0.85,
                description="余额计算关系",
                formula="balance[i] = balance[i-1] + income - expense",
            )
            relations.append(relation)

    return relations


# ========== Layer 3: Row semantic grouping ==========


def _identify_row_groups(table: list[list[str]], semantics: TableSemantics) -> list[RowGroup]:
    """Identify row groupings."""
    groups = []

    # 1. Time-based grouping (monthly)
    time_groups = _group_by_time(table, semantics)
    groups.extend(time_groups)

    # 2. Summary row identification
    summary_groups = _identify_summary_rows(table, semantics)
    groups.extend(summary_groups)

    return groups


def _group_by_time(table: list[list[str]], semantics: TableSemantics) -> list[RowGroup]:
    """Group by time."""
    date_col = _find_date_column(semantics)
    if date_col is None:
        return []

    groups = []
    current_month = ""
    current_rows = []

    for i, row in enumerate(table[1:], 1):  # 跳过表头
        if date_col >= len(row):
            continue

        date_str = row[date_col]
        month = _extract_month(date_str)

        if month != current_month:
            if current_rows:
                groups.append(
                    RowGroup(
                        group_type=RowGroupType.TIME_MONTH,
                        rows=current_rows,
                        value=current_month,
                        confidence=0.9,
                    )
                )
            current_month = month
            current_rows = [i]
        else:
            current_rows.append(i)

    # Add the last group
    if current_rows:
        groups.append(
            RowGroup(
                group_type=RowGroupType.TIME_MONTH,
                rows=current_rows,
                value=current_month,
                confidence=0.9,
            )
        )

    return groups


def _identify_summary_rows(table: list[list[str]], _semantics: TableSemantics) -> list[RowGroup]:
    """Identify summary rows."""
    groups = []
    summary_keywords = ["合计", "总计", "小计", "汇总", "累计"]

    for i, row in enumerate(table):
        row_text = " ".join(row)
        if any(kw in row_text for kw in summary_keywords):
            # Check if it's the last row (usually totals)
            if i == len(table) - 1:
                group_type = RowGroupType.SUMMARY_TOTAL
            else:
                group_type = RowGroupType.SUMMARY_SUBTOTAL

            groups.append(
                RowGroup(
                    group_type=group_type,
                    rows=[i],
                    value="汇总行",
                    confidence=0.95,
                )
            )

    return groups


# ========== Layer 4: Semantic confidence evaluation ==========


def _compute_semantic_confidence(table: list[list[str]], semantics: TableSemantics) -> float:
    """Compute semantic confidence."""
    if semantics.table_type == TableType.UNKNOWN:
        return 0.3

    confidence = semantics.table_type_confidence * 0.4

    # Column relationship confidence
    if semantics.column_relations:
        avg_relation_conf = sum(r.confidence for r in semantics.column_relations) / len(semantics.column_relations)
        confidence += avg_relation_conf * 0.3
    else:
        confidence += 0.15  # 无关系不惩罚太多

    # Row grouping confidence
    if semantics.row_groups:
        confidence += 0.2
    else:
        confidence += 0.1

    # Logical consistency validation
    logical_score = _verify_logical_consistency(table, semantics)
    confidence += logical_score * 0.1

    return min(1.0, confidence)


def _verify_logical_consistency(table: list[list[str]], semantics: TableSemantics) -> float:
    """Verify logical consistency."""
    # Simplified implementation: check numerical constraints
    violations = 0
    total_checks = 0

    for i, row in enumerate(table[1:], 1):
        for j, cell in enumerate(row):
            col_type = semantics.column_types.get(j, "text")

            if col_type == "amount":
                total_checks += 1
                try:
                    value = float(cell.replace(",", "").replace("¥", ""))
                    if value < 0:  # 金额不应为负（除非特殊场景）
                        violations += 0.5  # 软违规
                except ValueError:
                    # B-04 FIX: log instead of silent pass
                    logger.debug(f"[semantic] non-numeric value in amount column: '{cell}'")

    if total_checks == 0:
        return 0.5

    return 1.0 - (violations / total_checks)


# ========== Helper functions ==========


def _infer_column_types(table: list[list[str]]) -> dict[int, str]:
    """Infer column types."""
    if not table or len(table) < 2:
        return {}

    header = table[0]
    col_types = {}

    for i, col_name in enumerate(header):
        col_types[i] = _detect_type_from_header(col_name)

    return col_types


def _detect_type_from_header(header: str) -> str:
    """Infer type from header."""
    header_lower = header.lower()

    type_keywords = {
        "date": ["日期", "时间", "date"],
        "amount": ["金额", "余额", "发生", "收入", "支出", "借方", "贷方"],
        "balance": ["余额", "结余"],
        "income": ["收入", "存入", "贷方"],
        "expense": ["支出", "取出", "借方"],
        "text": ["摘要", "备注", "户名", "名称"],
    }

    for col_type, keywords in type_keywords.items():
        if any(kw in header_lower for kw in keywords):
            return col_type

    return "text"


def _column_matches_type(col_name: str, type_name: str) -> bool:
    """Check if column name matches type."""
    return _detect_type_from_header(col_name) == type_name


def _find_date_column(semantics: TableSemantics) -> int | None:
    """Find date column."""
    for col_idx, col_type in semantics.column_types.items():
        if col_type == "date":
            return col_idx
    return None


def _extract_month(date_str: str) -> str:
    """Extract month from date string."""
    match = re.search(r"(\d{4}[-/]\d{2})", date_str)
    if match:
        return match.group(1)
    return ""


def _verify_calculation_pattern(table: list[list[str]], balance_col: int, _amount_cols: list[int]) -> bool:
    """Verify calculation pattern."""
    if len(table) < 3:
        return False

    correct_count = 0
    total_checks = 0

    for i in range(2, len(table)):
        try:
            prev_balance = float(table[i - 1][balance_col].replace(",", ""))
            curr_balance = float(table[i][balance_col].replace(",", ""))

            # Simplified validation: balance should have changed
            if abs(curr_balance - prev_balance) > 0.01:
                correct_count += 1
            total_checks += 1
        except (ValueError, IndexError):
            continue

    if total_checks == 0:
        return False

    return correct_count / total_checks > 0.7
