"""
BaseTableParser — shared base class for cashflow table_document community plugins.

Implements the ParseResult → Community recognition pipeline for ledger-style documents:
extract identity KV fields, match table headers via ``ColumnMatcher``, normalize
rows, and return a canonical ``CanonicalPatch``. Subclasses supply only domain config
(``column_registry``, ``standard_fields``, ``scene_keywords``, ``identity_fields``).

Pipeline role: extended by ``wechat_payment``, ``alipay_payment``, and partially
by ``bank_statement`` community plugin; the canonical runner invokes
``recognize_facts`` on registered recognizers.

Key exports: ``BaseTableParser``.

Dependencies: ``Core canonical capability``, ``column_registry``, ``standardizer``, table access
via canonical ``ParseResult`` pages/tables and evidence.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

from docmirror.input.canonical.fact_patch import CanonicalPatch
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
_SUMMARY_ROW_RE = re.compile(r"^(?:(?:本页|本期|当页)?(?:收入|支出)?(?:合计|小计|总计))(?:[:：].*)?$")


def _is_summary_row(row: list[str]) -> bool:
    """Return true only for rows that are clearly summaries, not directions.

    Payment exports may legitimately place ``收入`` or ``支出`` in the first
    column.  A row carrying a date or transaction id is therefore always data.
    """
    cells = [str(cell or "").strip() for cell in row]
    if any(_ISO_DATE_RE.match(cell) or _ISO_DATETIME_RE.match(cell) for cell in cells):
        return False
    if any(re.match(r"^\d{16,}$", re.sub(r"\s+", "", cell)) for cell in cells):
        return False
    first_cell = cells[0] if cells else ""
    if _SUMMARY_ROW_RE.fullmatch(first_cell):
        return True
    return first_cell in {"收入", "支出"} and any("合计" in cell for cell in cells[1:])


class BaseTableParser(ABC):
    """Generic statement parser base class.

    Subclasses only need to implement these abstract attributes:
    - domain_name
    - display_name
    - scene_keywords
    - column_registry (Dict[str, ColumnMapping])
    - standard_fields (List[str])

    Optional overrides:
    - identity_fields
    - _recover_records_from_evidence
    """

    # ── Abstract attributes that subclasses must implement ──

    @property
    @abstractmethod
    def column_registry(self) -> dict[str, ColumnMapping]:
        """Column mapping registry."""
        ...

    @property
    @abstractmethod
    def standard_fields(self) -> list[str]:
        """Standardized field order (for normalized block)."""
        ...

    # ── Optional overrides ──

    @property
    def capability_id(self) -> str:
        return self.domain_name

    @property
    def identity_fields(self) -> Sequence[tuple[str, Sequence[str]]]:
        return ()

    # ── Public API ──

    def _extract_fact_components(
        self,
        parse_result,
        text: str = "",
    ) -> tuple[dict[str, dict], list[dict], list[str], dict[str, Any], str | dict]:
        """Extract reusable fact components without constructing an edition."""
        # Step 1: Extract KV header area
        identity_fields = self._extract_identity(parse_result)
        try:
            recovered_identity = self._recover_identity_from_evidence(parse_result)
        except Exception:
            logger.warning("[%s] canonical evidence identity recovery failed", self.domain_name, exc_info=True)
            recovered_identity = {}
        for field_name, detail in recovered_identity.items():
            identity_fields.setdefault(field_name, detail)
        if text:
            try:
                from docmirror.plugins._base.kv_community_extract import _recover_identity_fields_from_text

                recovered = _recover_identity_fields_from_text(text, self.identity_fields)
                for field_name, value in recovered.items():
                    identity_fields.setdefault(
                        field_name,
                        {
                            "raw_name": field_name,
                            "raw_value": value,
                            "normalized_value": self._normalize_identity(field_name, value),
                            "data_type": "string",
                            "source_refs": [{"source": "full_text"}],
                            "evidence_ids": [],
                        },
                    )
            except Exception:
                logger.debug("[%s] text identity recovery skipped", self.domain_name, exc_info=True)

        # Step 2: Extract transaction table
        tables = self._collect_tables(parse_result)

        # Step 3: Detect header
        header_row_idx, raw_headers, col_map = self._detect_headers(tables)

        # Step 4: Extract transaction records
        transactions = self._extract_records(tables, header_row_idx, raw_headers, col_map)
        if not transactions:
            try:
                transactions = self._recover_records_from_evidence(parse_result)
            except Exception:
                logger.warning("[%s] canonical evidence record recovery failed", self.domain_name, exc_info=True)

        # Step 5: Build records (raw + normalized)
        records = self._build_records(transactions)

        # Step 6: Summary statistics
        summary = self._build_summary(records)

        # Step 7: Period
        period = extract_period(text) or summary.get("period", {})

        return identity_fields, records, raw_headers, summary, period

    def recognize_facts(self, parse_result, text: str = "") -> CanonicalPatch:
        """Return canonical facts directly, without an edition envelope."""
        identity_fields, records, raw_headers, summary, period = self._extract_fact_components(parse_result, text)
        return self._fact_patch_from_components(
            identity_fields=identity_fields,
            records=records,
            raw_headers=raw_headers,
            summary=summary,
            period=period,
        )

    def _fact_patch_from_components(
        self,
        *,
        identity_fields: dict[str, dict],
        records: list[dict],
        raw_headers: list[str],
        summary: dict[str, Any],
        period: str | dict,
        extra_domain_facts: dict[str, Any] | None = None,
        warnings: Sequence[str] = (),
        confidence: float = 1.0,
    ) -> CanonicalPatch:
        """Build the shared ledger CanonicalPatch from already extracted facts."""
        scalar_fields: dict[str, Any] = {}
        evidence_ids: list[str] = []
        for key, detail in identity_fields.items():
            value: Any = detail
            if isinstance(detail, dict):
                value = next(
                    (
                        detail.get(candidate)
                        for candidate in ("normalized_value", "value", "raw_value")
                        if detail.get(candidate) not in (None, "")
                    ),
                    None,
                )
                evidence_ids.extend(str(item) for item in detail.get("evidence_ids", []) if str(item))
            if value not in (None, ""):
                scalar_fields[str(key)] = value

        canonical_records = [
            {
                **dict(record),
                "record_id": str(record.get("record_id") or f"records:r{index:06d}"),
            }
            for index, record in enumerate(records, start=1)
        ]
        domain_facts: dict[str, Any] = {
            **scalar_fields,
            "field_details": identity_fields,
            "summary": summary,
            "source_headers": list(raw_headers),
        }
        if isinstance(period, dict):
            if period.get("start"):
                domain_facts["period_start"] = period["start"]
            if period.get("end"):
                domain_facts["period_end"] = period["end"]
        domain_facts.update(extra_domain_facts or {})
        patch_warnings = tuple(str(item) for item in warnings if str(item))
        if not scalar_fields and not canonical_records:
            patch_warnings = (*patch_warnings, "no_fields_extracted")
        return CanonicalPatch(
            capability_id=self.domain_name,
            document_type=self.domain_name,
            domain_facts=domain_facts,
            datasets={"records": canonical_records} if canonical_records else {},
            warnings=patch_warnings,
            evidence_ids=tuple(dict.fromkeys(evidence_ids)),
            confidence=confidence,
            reason="native table recognizer facts",
        )

    # ── Step 1: KV header area extraction ──

    def _extract_identity(self, parse_result) -> dict[str, dict]:
        """Extract identity fields from canonical KV pairs.

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
                                "source_refs": [
                                    {
                                        "page": int(getattr(page, "page_number", 0) or 0),
                                        **({"bbox": list(kv.bbox)} if getattr(kv, "bbox", None) else {}),
                                    }
                                ],
                                "evidence_ids": list(getattr(kv, "evidence_ids", []) or []),
                            }
                            break

                # Generic field detection (try even when identity_config is empty)
                if "account_holder" not in fields and "兹证明" in key:
                    name = re.sub(r"\(.*", "", val).strip()
                    if name:
                        fields["account_holder"] = {
                            "raw_name": key,
                            "raw_value": val,
                            "normalized_value": name,
                            "data_type": "string",
                            "source_refs": [
                                {
                                    "page": int(getattr(page, "page_number", 0) or 0),
                                    **({"bbox": list(kv.bbox)} if getattr(kv, "bbox", None) else {}),
                                }
                            ],
                            "evidence_ids": list(getattr(kv, "evidence_ids", []) or []),
                        }
                if "account_number" not in fields and "证件号码" in key:
                    m = re.search(r"(\d{6,})", val)
                    if m:
                        fields["account_number"] = {
                            "raw_name": key,
                            "raw_value": val,
                            "normalized_value": m.group(1),
                            "data_type": "string",
                            "source_refs": [
                                {
                                    "page": int(getattr(page, "page_number", 0) or 0),
                                    **({"bbox": list(kv.bbox)} if getattr(kv, "bbox", None) else {}),
                                }
                            ],
                            "evidence_ids": list(getattr(kv, "evidence_ids", []) or []),
                        }
                if "currency" not in fields and key in ("币种", "Currency"):
                    fields["currency"] = {
                        "raw_name": key,
                        "raw_value": val,
                        "normalized_value": "CNY" if "人民" in val else val,
                        "data_type": "string",
                        "source_refs": [
                            {
                                "page": int(getattr(page, "page_number", 0) or 0),
                                **({"bbox": list(kv.bbox)} if getattr(kv, "bbox", None) else {}),
                            }
                        ],
                        "evidence_ids": list(getattr(kv, "evidence_ids", []) or []),
                    }

        return fields

    @staticmethod
    def _normalize_identity(field_name: str, raw_value: str) -> str:
        """Basic standardization of identity field values."""
        if field_name == "currency":
            if "人民" in raw_value:
                return "CNY"
            return raw_value
        return raw_value

    # ── Step 2: Collect tables ──

    def _collect_tables(self, parse_result) -> list[list[list[str]]]:
        """Collect all tables from ParseResult.

        优先级：
          1. logical_tables（已跨页合并的逻辑表）— 优先使用
          2. physical pages[].tables（每页原始表）— 旧版 fallback

        返回 [[[cell_text, ...], ...], ...] 结构。
        """
        out: list[list[list[str]]] = []

        if not parse_result or not hasattr(parse_result, "pages"):
            return out

        # Try logical tables first (composed cross-page)
        from docmirror.tables.access import get_logical_tables

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

        # Fallback: physical per-page tables (raw)
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

    # ── Step 3: Header detection ──

    def _detect_headers(
        self,
        tables: list[list[list[str]]],
    ) -> tuple[int, list[str], dict[str, int]]:
        """Detect header row.

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

    # ── Step 4: Extract transaction records ──

    def _extract_records(
        self,
        tables: list[list[list[str]]],
        header_row_idx: int,
        raw_headers: list[str],
        col_map: dict[str, int],
    ) -> list[dict[str, str]]:
        """Extract transaction rows from table.

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

            for row in tbl[header_row_idx + 1 :]:
                if not row or not any(str(c).strip() for c in row):
                    continue

                # Skip only unambiguous summaries; 收入/支出 may be valid directions.
                first_cell = str(row[0] or "").strip() if row else ""
                if _is_summary_row(row):
                    continue

                # First column validation: must be date or long number (transaction ID)
                if not _ISO_DATE_RE.match(first_cell) and not re.match(r"^\d{16,}", first_cell):
                    date_cell = next(
                        (
                            str(c).strip()
                            for c in row
                            if _ISO_DATE_RE.match(str(c).strip()) or _ISO_DATETIME_RE.match(str(c).strip())
                        ),
                        "",
                    )
                    if not date_cell:
                        continue

                # Extract using col_map
                if has_col_map:
                    txn: dict[str, str] = {}
                    for field_name, col_idx in col_map.items():
                        if col_idx < len(row):
                            txn[raw_headers[col_idx] if col_idx < len(raw_headers) else f"col_{col_idx}"] = str(
                                row[col_idx] or ""
                            ).strip()
                    if any(txn.values()):
                        transactions.append(txn)
                else:
                    # No col_map, use original column index
                    txn = {}
                    for i, cell in enumerate(row):
                        h = raw_headers[i] if i < len(raw_headers) else f"col_{i}"
                        txn[h] = str(cell or "").strip()
                    if any(txn.values()):
                        transactions.append(txn)

        return transactions

    def _recover_records_from_evidence(self, parse_result) -> list[dict[str, Any]]:
        """Optional coordinate-aware fallback for documents with no detected table.

        The default is deliberately empty.  Payment plugins override this only
        for issuer layouts whose column headers and row anchors are explicit in
        canonical evidence atoms.
        """
        return []

    def _recover_identity_from_evidence(self, parse_result) -> dict[str, dict[str, Any]]:
        """Optional positioned-text recovery for issuer narrative headers."""
        return {}

    @staticmethod
    def _evidence_identity_detail(
        field_name: str,
        raw_name: str,
        value: str,
        *,
        page_id: str = "page:0001",
        evidence_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Build the same evidence-preserving shape as KV identity extraction."""
        return {
            "raw_name": raw_name,
            "raw_value": value,
            "normalized_value": value,
            "data_type": "string",
            "source_refs": [{"source": "canonical_evidence_atoms", "page_id": page_id}],
            "evidence_ids": list(evidence_ids or []),
            "field_name": field_name,
        }

    @staticmethod
    def _evidence_text_atoms_by_page(parse_result) -> dict[str, list[dict[str, Any]]]:
        """Return usable canonical evidence atoms grouped by page id."""
        from docmirror.plugins._runtime.evidence_access import text_atoms

        atoms = text_atoms(parse_result)

        grouped: dict[str, list[dict[str, Any]]] = {}
        for atom in atoms:
            if not isinstance(atom, dict):
                continue
            page_id = str(atom.get("page_id") or "")
            text = str(atom.get("text") or "").strip()
            bbox = atom.get("bbox")
            if not page_id or not text or not isinstance(bbox, list) or len(bbox) < 4:
                continue
            grouped.setdefault(page_id, []).append(atom)
        return grouped

    # ── Step 5: Build records (raw + normalized) ──

    def _build_records(self, transactions: list[dict[str, Any]]) -> list[dict]:
        """Build standard records format.

        每条记录包含：
        - row_index: int
        - raw: dict (原始值，key 为来源表头)
        - canonical_raw: dict (原始值，key 为标准字段名，供字段审计)
        - normalized: dict (标准化值)
        """
        records: list[dict] = []

        for idx, raw_txn in enumerate(transactions, start=1):
            raw_public = public_record_raw(raw_txn)
            normalized = self._normalize(raw_public)
            canonical_raw = self._canonical_raw_values(raw_public, normalized)
            source = raw_txn.get("_source")
            if not isinstance(source, dict):
                source = {"source": "canonical_table", "source_row_index": idx - 1}
            records.append(
                {
                    "row_index": idx,
                    "raw": raw_public,
                    "canonical_raw": canonical_raw,
                    "normalized": normalized,
                    "source": source,
                }
            )

        return records

    def _canonical_raw_values(
        self,
        raw_txn: dict[str, Any],
        normalized: dict[str, Any],
    ) -> dict[str, Any]:
        """Map source values onto canonical field keys before facts are sealed."""
        canonical_raw: dict[str, Any] = {}
        for canonical_name, mapping in self.column_registry.items():
            raw_value: Any = ""
            for raw_key, candidate in raw_txn.items():
                if raw_key == canonical_name or raw_key in (mapping.aliases or []):
                    raw_value = candidate
                    break
            if raw_value in (None, ""):
                for raw_key, candidate in raw_txn.items():
                    if canonical_name in raw_key or raw_key in canonical_name:
                        raw_value = candidate
                        break
            canonical_raw[mapping.field] = raw_value

        if "amount_cny" in normalized:
            canonical_raw["amount_cny"] = canonical_raw.get("amount", "")
        if "original_signed_amount" in normalized:
            canonical_raw["original_signed_amount"] = canonical_raw.get("amount", "")
        if "date" in normalized:
            canonical_raw["date"] = canonical_raw.get("date") or canonical_raw.get("timestamp", "")
        for key, value in normalized.items():
            canonical_raw.setdefault(key, raw_txn.get(key, value))
        return canonical_raw

    def _normalize(self, raw_txn: dict[str, str]) -> dict[str, Any]:
        """Normalize a single raw transaction.

        使用 column_registry 中的映射进行：
        - 枚举转换（方向、类型等）
        - 金额转换 str → float
        - 时间格式化
        - 字段默认值
        """
        normalized: dict[str, Any] = {}

        # Build field values using column_registry canonical_name first
        for canonical_name, mapping in self.column_registry.items():
            # Find matching key in raw_txn
            raw_val = ""
            for raw_key, raw_v in raw_txn.items():
                if raw_key == canonical_name or (mapping.aliases and raw_key in mapping.aliases):
                    raw_val = raw_v
                    break
            if not raw_val:
                # Substring match
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
            elif mapping.field == "date" or mapping.format_hint == "date":
                ts = normalize_timestamp(raw_val)
                normalized[mapping.field] = ts[:10] if ts and len(ts) >= 10 else ts
            else:
                normalized[mapping.field] = raw_val

        # Ensure all standard_fields have default values
        for field in self.standard_fields:
            if field not in normalized:
                if field == "amount":
                    normalized[field] = None
                    normalized["amount_cny"] = None
                else:
                    normalized[field] = ""

        if not normalized.get("date") and normalized.get("timestamp"):
            ts = str(normalized["timestamp"])
            if len(ts) >= 10:
                normalized["date"] = ts[:10]

        return normalized

    # ── Step 6: Summary statistics ──

    @staticmethod
    def _build_summary(records: list[dict]) -> dict[str, Any]:
        """Build summary statistics.

        包括：
        - total_rows
        - total_income / total_expense / net_flow
        - period (从记录中推断)
        - statistics (count / avg / max)
        """
        income_recs = [r for r in records if r["normalized"].get("direction") == "income"]
        expense_recs = [r for r in records if r["normalized"].get("direction") == "expense"]
        other_recs = [r for r in records if r["normalized"].get("direction") not in ("income", "expense")]

        income_amounts = [r["normalized"]["amount"] for r in income_recs if r["normalized"].get("amount") is not None]
        expense_amounts = [r["normalized"]["amount"] for r in expense_recs if r["normalized"].get("amount") is not None]

        total_income = round(sum(income_amounts), 2) if income_amounts else 0.0
        total_expense = round(sum(expense_amounts), 2) if expense_amounts else 0.0

        all_dates = sorted(
            str(r["normalized"]["date"])[:10]
            for r in records
            if _ISO_DATE_RE.match(str(r["normalized"].get("date") or "")[:10])
        )
        all_ts = sorted(r["normalized"]["timestamp"] for r in records if r["normalized"].get("timestamp"))
        period: dict[str, str] = {}
        if len(all_dates) >= 2:
            period = {"start": all_dates[0], "end": all_dates[-1]}
        elif len(all_dates) == 1:
            period = {"start": all_dates[0], "end": all_dates[0]}
        elif len(all_ts) >= 2:
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


def public_record_raw(raw: dict) -> dict:
    """Strip parser-internal keys (prefixed with ``_``) from a raw record.

    Returns a new dict containing only public-facing keys. Used when
    serializing edition output to prevent internal metadata from leaking
    into the consumer-facing ``raw`` field.

    Example:
        >>> public_record_raw({"_norm": {}, "amount": "100", "_style_id": "x"})
        {"amount": "100"}
    """
    return {k: v for k, v in raw.items() if not k.startswith("_")}
