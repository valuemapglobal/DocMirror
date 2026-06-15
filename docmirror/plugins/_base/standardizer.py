"""
标准器 — 社区版基础标准化工具
================================

社区版只做三类标准化：
1. 金额：str → float（去逗号/¥/空格）
2. 时间：多种格式 → ISO8601
3. 枚举：中文 → 英文

不做：质量评分、规则校验、数据脱敏。
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any


def normalize_amount(raw: str) -> float | None:
    """金额标准化。

    - 去除 ¥ ￥ , 空格
    - 去除前导 +
    - 返回 float 或 None
    """
    cleaned = re.sub(r"[¥￥,，\s元圆]", "", raw.strip())
    if not cleaned:
        return None
    cleaned = cleaned.lstrip("+")
    try:
        return round(float(cleaned), 2)
    except (ValueError, TypeError):
        return None


def normalize_timestamp(raw: str) -> str:
    """时间标准化。

    支持格式：
    - 2022-01-01 10:30:39
    - 2022-01-01 10:30
    - 2022-01-01
    - 2022/01/01 10:30:39
    - 2022年01月01日 10:30:39
    - 2022-09-2810:30:39（支付宝/OCR 缺空格）
    """
    raw = raw.strip()
    if not raw:
        return ""

    # 如果已是 ISO8601（含 T），直接返回
    if re.match(r"^\d{4}-\d{2}-\d{2}T", raw):
        return raw

    # 统一分隔符
    cleaned = raw.replace("/", "-").replace("年", "-").replace("月", "-").replace("日", " ").strip()

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned, fmt).isoformat()
        except ValueError:
            continue

    # 支付宝/OCR：日期与时间之间缺空格，如 2022-09-2810:30:39
    m = re.match(r"^(\d{4}-\d{2}-\d{2})(\d{1,2}:\d{2}(?::\d{2})?)$", cleaned)
    if m:
        date_part, time_part = m.group(1), m.group(2)
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(f"{date_part} {time_part}", fmt).isoformat()
            except ValueError:
                continue

    # 紧凑日期：20220505
    m = re.match(r"^(\d{4})(\d{2})(\d{2})$", cleaned)
    if m:
        try:
            return datetime.strptime(cleaned, "%Y%m%d").date().isoformat()
        except ValueError:
            pass

    # 紧凑格式：20220928 103039
    m = re.match(r"(\d{4})(\d{2})(\d{2})\s*(\d{2})(\d{2})(\d{2})", cleaned)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}T{m.group(4)}:{m.group(5)}:{m.group(6)}"

    return raw  # 无法标准化，保留原始值


def normalize_enum(raw: str, enum_map: dict[str, str]) -> str:
    """枚举标准化。

    :param raw: 原始中文值
    :param enum_map: 映射表，如 {"收入": "income", "支出": "expense"}
    :returns: 标准化后的英文值，未匹配则保留原始值
    """
    if not raw:
        return ""
    return enum_map.get(raw, raw)


def normalize_record(
    raw_txn: dict[str, str],
    col_map: dict[str, str],
    column_registry: dict,
    standard_fields: list[str],
) -> dict[str, Any]:
    """对单条交易记录进行标准化。

    :param raw_txn: 原始行数据，key 为表头列名
    :param col_map: {标准字段名: 列索引} 或 {标准字段名: 表头原列名}
    :param column_registry: 列映射注册表
    :param standard_fields: 标准化字段顺序
    :returns: 标准化后的 dict
    """
    normalized: dict[str, Any] = {}
    raw_by_field: dict[str, str] = {}

    # 将 col_map 转换为 {标准字段名: 原始值}
    for field_name, col_ref in col_map.items():
        if isinstance(col_ref, int):
            # col_map 是 {field: index} 格式
            # 需要从 raw_txn 中找到对应列
            pass
        else:
            # col_ref 是原始列名
            raw_by_field[field_name] = raw_txn.get(col_ref, "")

    # 如果 col_map 是 {field: index} 格式，用 raw_txn 的 key 匹配
    if not raw_by_field:
        for raw_key, raw_val in raw_txn.items():
            for field_name, col_ref in col_map.items():
                if isinstance(col_ref, int):
                    # 通过索引无法反推列名，已经错过了
                    pass

    # 更通用的方式：col_map 是 {标准字段名: 原始列索引}
    # 而 raw_txn 的 key 是表头列名（原始列名）
    # 我们需要建立 原始列名 ↔ 标准字段名 的双向映射
    # 通过 column_registry 来建立

    # 方法：先找到每个标准字段对应的原始值
    keys_to_fields: dict[str, str] = {}
    for canonical_name, mapping in column_registry.items():
        keys_to_fields[canonical_name] = mapping.field

    for raw_key, raw_val in raw_txn.items():
        # 尝试匹配 canonical_name
        matched_field = None
        for canonical_name, mapping in column_registry.items():
            if raw_key == canonical_name or (mapping.aliases and raw_key in mapping.aliases):
                matched_field = mapping.field
                break
        # 子串匹配
        if matched_field is None:
            for canonical_name, mapping in column_registry.items():
                if canonical_name in raw_key or raw_key in canonical_name:
                    matched_field = mapping.field
                    break

        if matched_field:
            mapping = column_registry.get(
                next((k for k, v in column_registry.items() if v.field == matched_field), ""),
                None,
            )
            if mapping and mapping.enum_map:
                normalized[matched_field] = normalize_enum(raw_val, mapping.enum_map)
            elif mapping and mapping.field == "amount":
                normalized[matched_field] = normalize_amount(raw_val)
            elif mapping and mapping.field == "timestamp":
                normalized[matched_field] = normalize_timestamp(raw_val)
            else:
                normalized[matched_field] = raw_val
        else:
            # 无法匹配的字段，按原样保留
            normalized[f"raw_{raw_key}"] = raw_val

    # 确保所有 standard_fields 都有值
    for field in standard_fields:
        if field not in normalized:
            normalized[field] = "" if field != "amount" else None

    return normalized


def extract_period(text: str) -> str:
    """从全文文本中提取查询时间段。"""
    m = re.search(
        r"(\d{4}[-./年]\d{1,2}[-./月]\d{1,2}日?\s*[~\-至]\s*\d{4}[-./年]\d{1,2}[-./月]\d{1,2}日?)",
        text,
    )
    return m.group(1) if m else ""
