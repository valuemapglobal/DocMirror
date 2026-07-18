# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
WeChat payment community domain plugin (v2.0).

Premium community plugin for WeChat transaction export PDFs. Extends ``BaseTableParser``
with WeChat-specific column registry, scene keywords, identity field specs, and custom
row normalization (trade number cleanup, direction mapping).

Pipeline role: one of six premium plugins discovered by ``community`` and executed
via ``runner._run_community_extract`` → ``extract_from_mirror``.

Archetype: ``table_document``; domain: ``cashflow_payment``; support level: L2.

Key exports: ``WeChatPaymentPlugin``, ``plugin``, ``WECHAT_COLUMN_REGISTRY``,
``WECHAT_STANDARD_FIELDS``, ``WECHAT_IDENTITY_FIELDS``, ``WECHAT_SCENE_KEYWORDS``.

Dependencies: ``_base.base_table_parser``, ``_base.column_registry``, ``standardizer``.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence

from docmirror.plugins._base.base_table_parser import BaseTableParser
from docmirror.plugins._base.column_registry import ColumnMapping
from docmirror.plugins._base.standardizer import normalize_amount

logger = logging.getLogger(__name__)

WECHAT_COLUMN_REGISTRY: dict[str, ColumnMapping] = {
    "收/支/其他": ColumnMapping(
        field="direction",
        enum_map={"收入": "income", "支出": "expense", "其他": "other", "/": "other"},
        aliases=["收/支", "收支其他"],
    ),
    "金额(元)": ColumnMapping(
        field="amount",
        unit="CNY",
        aliases=["金额", "交易金额（元）", "交易金额(元)", "金额（元）", "Amount", "Amount (CNY)"],
    ),
    "交易单号": ColumnMapping(
        field="trade_no",
        aliases=["交易单号/交易编号", "商户订单号", "微信单号"],
    ),
    "交易时间": ColumnMapping(
        field="timestamp",
        format_hint="datetime",
        aliases=["交易日期", "时间", "日期", "Date", "Transaction Date"],
    ),
    "交易对方": ColumnMapping(
        field="counter_party",
        aliases=["对方", "交易对手", "对方名称"],
    ),
    "交易类型": ColumnMapping(
        field="transaction_type",
        aliases=["类型", "交易方式", "支付方式", "Transaction", "Description"],
    ),
    "交易方式": ColumnMapping(
        field="transaction_method",
        aliases=["支付方式", "交易渠道", "Payment Method"],
    ),
    "交易对象": ColumnMapping(
        field="counter_object",
        aliases=["对象", "对方账户", "对方账号"],
    ),
    "余额": ColumnMapping(field="balance", unit="CNY", aliases=["Balance", "Balance (CNY)"]),
    "备注": ColumnMapping(field="note", aliases=["Note", "Remarks"]),
}

WECHAT_STANDARD_FIELDS = [
    "direction",
    "counter_party",
    "transaction_type",
    "transaction_method",
    "counter_object",
    "amount",
    "trade_no",
    "timestamp",
    "balance",
    "note",
]

WECHAT_SCENE_KEYWORDS = (
    "微信支付交易明细证明",
    "财付通",
    "微信流水",
    "WeChat Pay",
    "微信支付",
)

WECHAT_DEFAULT_COLUMNS = list(WECHAT_COLUMN_REGISTRY.keys())

_MIRROR_DATE_RE = re.compile(r"^20\d{2}-\d{2}-\d{2}$")
_MIRROR_TIME_RE = re.compile(r"^\d{2}:\d{2}:\d{2}$")
_MIRROR_AMOUNT_RE = re.compile(r"^-?\d[\d,]*\.\d{2}$")
_MIRROR_DIRECTIONS = frozenset({"收入", "支出", "其他"})
_MIRROR_HEADERS = (
    "交易单号",
    "交易时间",
    "交易类型",
    "收/支/其他",
    "交易方式",
    "金额(元)",
    "交易对方",
    "商户单号",
)
_DATETIME_RE = r"20\d{2}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}"

WECHAT_IDENTITY_FIELDS: Sequence[tuple[str, Sequence[str]]] = (
    ("account_holder", ("户名", "姓名", "Account holder", "User")),
    ("account_number", ("账号", "卡号", "Account number", "WeChat ID")),
    ("query_period", ("查询时间段", "起始日期", "终止日期", "Query period", "Statement Period")),
    ("currency", ("币种", "Currency")),
)


class WeChatPaymentPlugin(BaseTableParser):
    """Community v2.0: WeChat Pay statement plugin."""

    @property
    def domain_name(self) -> str:
        return "wechat_payment"

    @property
    def display_name(self) -> str:
        return "WeChat Payment (Community)"

    @property
    def column_registry(self) -> dict[str, ColumnMapping]:
        return WECHAT_COLUMN_REGISTRY

    @property
    def standard_fields(self) -> list[str]:
        return WECHAT_STANDARD_FIELDS

    @property
    def identity_fields(self) -> Sequence[tuple[str, Sequence[str]]]:
        return WECHAT_IDENTITY_FIELDS

    def _recover_identity_from_mirror(self, parse_result) -> dict[str, dict[str, object]]:
        atoms_by_page = self._mirror_text_atoms_by_page(parse_result)
        if not atoms_by_page:
            return {}
        page_id = sorted(atoms_by_page)[0]
        atoms = sorted(
            atoms_by_page[page_id],
            key=lambda atom: (float(atom["bbox"][1]), float(atom["bbox"][0])),
        )
        text = " ".join(str(atom.get("text") or "").strip() for atom in atoms)
        patterns = {
            "certificate_number": ("编号", r"编号\s*[:：]\s*([0-9A-Za-z]+)"),
            "account_holder": ("兹证明", r"兹证明\s*[:：]\s*(.+?)\s*[（(]身份证"),
            "id_number": ("身份证", r"身份证\s*[:：]\s*([0-9Xx*]+)"),
            "account_number": ("微信号", r"微信号\s*[:：]\s*([A-Za-z0-9_*\-]+)"),
            "query_period": (
                "交易明细对应时间段",
                rf"交易明细对应时间段\s*({_DATETIME_RE})\s*至\s*({_DATETIME_RE})",
            ),
            "currency": ("币种", r"币种\s*[:：]?\s*([^\s/，,]+)"),
            "unit": ("单位", r"单位\s*[:：]?\s*([^\s，,]+)"),
        }
        recovered: dict[str, dict[str, object]] = {}
        for field_name, (label, pattern) in patterns.items():
            match = re.search(pattern, text)
            if not match:
                continue
            value = " 至 ".join(match.groups()) if field_name == "query_period" else match.group(1).strip()
            if value:
                recovered[field_name] = self._mirror_identity_detail(field_name, label, value, page_id=page_id)
        return recovered

    def build_domain_data(self, metadata, entities):
        """Lightweight KV projection used when mirror-native extraction is unavailable."""
        from docmirror.plugins._base.dec_builder import build_dec_kv

        account_holder = str(entities.get("account_holder", metadata.get("Account holder", "")))
        account_number = str(entities.get("account_number", metadata.get("Account number", "")))
        transactions = entities.get("transactions", metadata.get("transactions", []))
        total_income = 0.0
        total_expense = 0.0
        total_transactions = len(transactions) if isinstance(transactions, list) else 0

        if isinstance(transactions, list):
            for txn in transactions:
                try:
                    amount_str = txn.get("金额(元)", txn.get("金额", "0"))
                    amt = normalize_amount(amount_str) or 0.0
                except (ValueError, AttributeError):
                    continue
                direction = txn.get("收/支", txn.get("收/支/其他", ""))
                if "收入" in direction or "存入" in direction:
                    total_income += amt
                elif "支出" in direction or "取出" in direction:
                    total_expense += amt

        return build_dec_kv(
            "wechat_payment",
            {
                "account_holder": account_holder,
                "account_number": account_number,
                "total_transactions": total_transactions,
                "total_income": total_income,
                "total_expense": total_expense,
            },
        )

    def _detect_headers(
        self,
        tables: list[list[list[str]]],
    ) -> tuple[int, list[str], dict[str, int]]:
        for table in tables:
            for row_index, row in enumerate(table[:12]):
                joined = " ".join(str(cell or "") for cell in row).lower()
                if "date" in joined and "amount" in joined and ("transaction" in joined or "description" in joined):
                    return row_index, ["Date", "Transaction", "Amount", "Balance", "Note"], {"__english__": 0}
        return super()._detect_headers(tables)

    def _extract_records(
        self,
        tables: list[list[list[str]]],
        header_row_idx: int,
        raw_headers: list[str],
        col_map: dict[str, int],
    ) -> list[dict[str, str]]:
        if "__english__" not in col_map:
            return super()._extract_records(tables, header_row_idx, raw_headers, col_map)
        transactions: list[dict[str, str]] = []
        for table in tables:
            for row in table[header_row_idx + 1 :]:
                joined = " ".join(str(cell or "").strip() for cell in row if str(cell or "").strip())
                date_match = re.match(r"^(\d{4}-\d{2}-\d{2})\s+", joined)
                if not date_match:
                    continue
                tail = joined[date_match.end() :]
                amounts = list(re.finditer(r"[-+]?\d[\d,]*\.\d{2}", tail))
                if not amounts:
                    continue
                description = tail[: amounts[0].start()].strip()
                amount = amounts[0].group(0)
                balance = amounts[1].group(0) if len(amounts) > 1 else ""
                note = tail[amounts[1].end() :].strip() if len(amounts) > 1 else tail[amounts[0].end() :].strip()
                transactions.append(
                    {
                        "Date": date_match.group(1),
                        "Transaction": description,
                        "Amount": amount,
                        "Balance": balance,
                        "Note": note,
                    }
                )
        return transactions

    def _recover_records_from_mirror(self, parse_result) -> list[dict[str, object]]:
        """Recover WeChat issuer rows from positioned Mirror text atoms."""
        atoms_by_page = self._mirror_text_atoms_by_page(parse_result)
        if not atoms_by_page:
            return []

        all_atoms = [atom for atoms in atoms_by_page.values() for atom in atoms]
        header_texts = {str(atom.get("text") or "").strip() for atom in all_atoms}
        composite_header = next(
            (
                atom
                for atom in all_atoms
                if all(
                    marker in str(atom.get("text") or "")
                    for marker in ("交易时间", "交易类型", "收/支/其他", "金额(元)")
                )
            ),
            None,
        )
        counter_party_header = next(
            (atom for atom in all_atoms if str(atom.get("text") or "").strip() == "交易对方"),
            None,
        )
        trade_header = next(
            (atom for atom in all_atoms if str(atom.get("text") or "").strip() == "交易单号"),
            None,
        )
        merchant_header = next(
            (atom for atom in all_atoms if str(atom.get("text") or "").strip() == "商户单号"),
            None,
        )
        if not {"交易单号", "交易对方", "商户单号"}.issubset(header_texts):
            return []
        if any(atom is None for atom in (composite_header, counter_party_header, trade_header, merchant_header)):
            return []
        composite_left = float(composite_header["bbox"][0])
        composite_width = float(composite_header["bbox"][2]) - composite_left
        if composite_width <= 0:
            return []
        composite_anchors = [composite_left + composite_width * index / 5 for index in range(5)]
        anchors = [
            float(trade_header["bbox"][0]),
            *composite_anchors,
            float(counter_party_header["bbox"][0]),
            float(merchant_header["bbox"][0]),
        ]
        if anchors != sorted(anchors):
            return []
        bounds = [float("-inf"), *((left + right) / 2 for left, right in zip(anchors, anchors[1:])), float("inf")]
        date_x = anchors[1]

        recovered: list[dict[str, object]] = []
        for page_id in sorted(atoms_by_page):
            atoms = atoms_by_page[page_id]
            dates = sorted(
                (
                    (float(atom["bbox"][1]), str(atom.get("text") or "").strip(), atom)
                    for atom in atoms
                    if abs(float(atom["bbox"][0]) - date_x) <= 12.0
                    and _MIRROR_DATE_RE.fullmatch(str(atom.get("text") or "").strip())
                ),
                key=lambda item: item[0],
            )
            for index, (row_y, date, date_atom) in enumerate(dates):
                if index + 1 < len(dates):
                    row_end = dates[index + 1][0]
                else:
                    prior_gap = row_y - dates[index - 1][0] if index > 0 else 40.0
                    row_end = row_y + max(prior_gap * 1.5, 40.0)
                row_atoms = sorted(
                    (atom for atom in atoms if row_y - 0.5 <= float(atom["bbox"][1]) < row_end - 0.5),
                    key=lambda atom: (float(atom["bbox"][1]), float(atom["bbox"][0])),
                )

                def column_atoms(column_index: int) -> list[dict]:
                    return [
                        atom
                        for atom in row_atoms
                        if bounds[column_index] <= float(atom["bbox"][0]) < bounds[column_index + 1]
                    ]

                def column_text(column_index: int) -> str:
                    return "".join(str(atom.get("text") or "").strip() for atom in column_atoms(column_index))

                direction_atom = next(
                    (atom for atom in column_atoms(3) if str(atom.get("text") or "").strip() in _MIRROR_DIRECTIONS),
                    None,
                )
                amount_atom = next(
                    (
                        atom
                        for atom in column_atoms(5)
                        if _MIRROR_AMOUNT_RE.fullmatch(str(atom.get("text") or "").strip())
                    ),
                    None,
                )
                time_atom = next(
                    (
                        atom
                        for atom in column_atoms(1)
                        if _MIRROR_TIME_RE.fullmatch(str(atom.get("text") or "").strip())
                    ),
                    None,
                )
                trade_atoms = [atom for atom in column_atoms(0) if str(atom.get("text") or "").strip().isdigit()]
                trade_no = "".join(str(atom.get("text") or "").strip() for atom in trade_atoms)
                if direction_atom is None or amount_atom is None or time_atom is None or not trade_no:
                    continue

                evidence_atoms = [date_atom, *row_atoms]
                recovered.append(
                    {
                        "收/支/其他": str(direction_atom.get("text") or "").strip(),
                        "金额(元)": str(amount_atom.get("text") or "").strip(),
                        "交易单号": trade_no,
                        "交易时间": f"{date} {str(time_atom.get('text') or '').strip()}",
                        "交易类型": column_text(2),
                        "交易方式": column_text(4),
                        "交易对方": column_text(6),
                        "商户单号": column_text(7),
                        "_source": {
                            "source": "mirror_text_atoms",
                            "page_id": page_id,
                            "evidence_ids": [
                                str(atom.get("id") or "") for atom in evidence_atoms if str(atom.get("id") or "")
                            ],
                        },
                    }
                )
        return recovered

    def _normalize(self, raw_txn: dict[str, str]) -> dict[str, object]:
        normalized = super()._normalize(raw_txn)
        amount = normalized.get("amount")
        if isinstance(amount, (int, float)):
            normalized["original_signed_amount"] = amount
            if not normalized.get("direction"):
                normalized["direction"] = "expense" if amount < 0 else "income"
            normalized["amount"] = abs(amount)
            normalized["amount_cny"] = abs(amount)
        return normalized


plugin = WeChatPaymentPlugin()
