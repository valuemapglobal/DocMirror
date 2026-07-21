# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Recover high-confidence split debit/credit ledgers from canonical evidence atoms."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

_DATE_RE = re.compile(r"^(?:20\d{6}|20\d{2}[-/]\d{1,2}[-/]\d{1,2})$")
_MONEY_RE = re.compile(r"^-?\d[\d,]*\.\d{2}$")
_COMPOSITE_MARKERS = ("支出", "收入", "账户余额")
_OUTPUT_HEADER = [
    "序号",
    "交易日期",
    "交易流水号",
    "支出金额",
    "收入金额",
    "余额",
    "对方账号",
    "对方户名",
    "对方行号",
    "对方行名",
    "交易渠道",
    "用途",
    "摘要",
]


def recover_evidence_atom_bank_tables(parse_result: Any) -> list[list[list[str]]]:
    """Return one canonical table when issuer headers and column geometry agree."""
    atoms_by_page = _atoms_by_page(parse_result)
    if not atoms_by_page:
        return []
    all_atoms = [atom for atoms in atoms_by_page.values() for atom in atoms]

    header_names = (
        "序号",
        "交易日期",
        "交易流水号",
        "对方账号",
        "对方户名",
        "对方行号",
        "对方行名",
        "交易渠道",
        "用途",
        "摘要",
    )
    headers = {name: _first_exact(all_atoms, name) for name in header_names}
    composite_header = next(
        (atom for atom in all_atoms if all(marker in str(atom.get("text") or "") for marker in _COMPOSITE_MARKERS)),
        None,
    )
    if composite_header is None or any(atom is None for atom in headers.values()):
        return []

    composite_left = float(composite_header["bbox"][0])
    composite_right = float(composite_header["bbox"][2])
    endpoints = _money_column_endpoints(all_atoms, composite_left, composite_right)
    if len(endpoints) != 3:
        return []
    expense_end, income_end, balance_end = endpoints

    anchors = {name: float(atom["bbox"][0]) for name, atom in headers.items() if atom is not None}
    if [anchors[name] for name in header_names] != sorted(anchors[name] for name in header_names):
        return []
    sequence_right = (anchors["序号"] + anchors["交易日期"]) / 2
    date_x = anchors["交易日期"]
    reference_left = (anchors["交易日期"] + anchors["交易流水号"]) / 2
    reference_right = (anchors["交易流水号"] + composite_left) / 2
    account_left = (composite_right + anchors["对方账号"]) / 2
    text_columns = ("对方账号", "对方户名", "对方行号", "对方行名", "交易渠道", "用途", "摘要")
    text_bounds = [
        account_left,
        *((anchors[left] + anchors[right]) / 2 for left, right in zip(text_columns, text_columns[1:])),
        float("inf"),
    ]

    rows: list[list[str]] = []
    for page_id in sorted(atoms_by_page):
        atoms = atoms_by_page[page_id]
        dates = sorted(
            (
                (float(atom["bbox"][1]), str(atom.get("text") or "").strip())
                for atom in atoms
                if abs(float(atom["bbox"][0]) - date_x) <= 12.0
                and _DATE_RE.fullmatch(str(atom.get("text") or "").strip())
            ),
            key=lambda item: item[0],
        )
        for index, (row_y, date) in enumerate(dates):
            if index + 1 < len(dates):
                row_end = dates[index + 1][0]
            else:
                footer_starts = [
                    float(atom["bbox"][1])
                    for atom in atoms
                    if float(atom["bbox"][1]) > row_y
                    and any(marker in str(atom.get("text") or "") for marker in ("风险提示", "本回单"))
                ]
                row_end = min(footer_starts, default=float("inf"))
            row_atoms = [atom for atom in atoms if row_y - 0.5 <= float(atom["bbox"][1]) < row_end - 0.5]
            money = [
                atom
                for atom in row_atoms
                if composite_left - 2.0 <= float(atom["bbox"][0])
                and float(atom["bbox"][2]) <= composite_right + 3.0
                and _MONEY_RE.fullmatch(str(atom.get("text") or "").strip())
            ]
            expense = _money_at_endpoint(money, expense_end)
            income = _money_at_endpoint(money, income_end)
            balance = _money_at_endpoint(money, balance_end)
            if not balance or bool(expense) == bool(income):
                continue
            rows.append(
                [
                    _column_text(row_atoms, float("-inf"), sequence_right),
                    date,
                    _column_text(row_atoms, reference_left, reference_right),
                    expense,
                    income,
                    balance,
                    *[
                        _column_text(row_atoms, text_bounds[column_index], text_bounds[column_index + 1])
                        for column_index in range(len(text_columns))
                    ],
                ]
            )
    return [[_OUTPUT_HEADER, *rows]] if rows else []


def _atoms_by_page(parse_result: Any) -> dict[str, list[dict[str, Any]]]:
    from docmirror.plugins._runtime.evidence_access import text_atoms

    atoms = text_atoms(parse_result)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for atom in atoms:
        if not isinstance(atom, dict):
            continue
        page_id = str(atom.get("page_id") or "")
        bbox = atom.get("bbox")
        text = str(atom.get("text") or "").strip()
        if page_id and text and isinstance(bbox, list) and len(bbox) >= 4:
            grouped[page_id].append(atom)
    return dict(grouped)


def _first_exact(atoms: list[dict[str, Any]], text: str) -> dict[str, Any] | None:
    return next((atom for atom in atoms if str(atom.get("text") or "").strip() == text), None)


def _money_column_endpoints(atoms: list[dict[str, Any]], left: float, right: float) -> list[float]:
    rounded_ends = [
        round(float(atom["bbox"][2]), 1)
        for atom in atoms
        if left - 2.0 <= float(atom["bbox"][0])
        and float(atom["bbox"][2]) <= right + 3.0
        and _MONEY_RE.fullmatch(str(atom.get("text") or "").strip())
    ]
    common = [value for value, count in Counter(rounded_ends).most_common() if count >= 2]
    return sorted(common) if len(common) == 3 else []


def _money_at_endpoint(atoms: list[dict[str, Any]], endpoint: float) -> str:
    atom = next((atom for atom in atoms if abs(float(atom["bbox"][2]) - endpoint) <= 1.0), None)
    return str(atom.get("text") or "").strip() if atom else ""


def _column_text(atoms: list[dict[str, Any]], left: float, right: float) -> str:
    selected = sorted(
        (atom for atom in atoms if left <= float(atom["bbox"][0]) < right),
        key=lambda atom: (float(atom["bbox"][1]), float(atom["bbox"][0])),
    )
    return "".join(str(atom.get("text") or "").strip() for atom in selected)


__all__ = ["recover_evidence_atom_bank_tables"]
