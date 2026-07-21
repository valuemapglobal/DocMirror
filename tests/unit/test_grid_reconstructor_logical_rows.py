# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for borderless logical-row grid reconstruction."""

from __future__ import annotations

from dataclasses import dataclass

from docmirror.layout.profile.registry import get_profile
from docmirror.tables.best_candidate import ExtractCandidate, pick_best_candidate
from docmirror.tables.char.grid_reconstructor import detect_table_via_grid


@dataclass
class _FakePage:
    chars: list[dict]
    words: list[dict]

    def extract_words(self, **_kwargs):
        return self.words


def _word(text: str, x0: float, top: float, width: float | None = None) -> dict:
    width = width if width is not None else max(4.0, len(text) * 8.0)
    return {"text": text, "x0": x0, "x1": x0 + width, "top": top, "bottom": top + 8}


def _chars(text: str, x0: float, top: float, step: float = 4.0) -> list[dict]:
    out = []
    for idx, ch in enumerate(text):
        cx = x0 + idx * step
        out.append({"text": ch, "x0": cx, "x1": cx + step * 0.75, "top": top, "bottom": top + 8})
    return out


def _ledger_page() -> _FakePage:
    headers = [
        ("序号", 28),
        ("交易日期", 59),
        ("交易时间", 104),
        ("摘要", 197),
        ("凭证种类", 274),
        ("借方发生额", 315),
        ("贷方发生额", 365),
        ("余额", 427),
        ("对方账户", 469),
        ("对方户名", 524),
    ]
    chars: list[dict] = []
    words: list[dict] = []
    for text, x0 in headers:
        chars.extend(_chars(text, x0, 137))
        words.append(_word(text, x0, 137))

    rows = [
        (
            "1",
            "2022-06-01",
            "16:59:43",
            "往来款",
            "7,900.00",
            "",
            "18.75",
            "1104010309000",
            "388824",
            "镇江小松鼠",
            "公司",
        ),
        ("2", "2022-06-02", "15:13:28", "收费", "2.00", "", "16.75", "7065010736000", "0033", "手续费收", "入"),
    ]
    tops = [159, 188]
    for top, row in zip(tops, rows, strict=True):
        seq, date, time, summary, debit, credit, balance, acct_a, acct_b, name_a, name_b = row
        chars.extend(_chars(seq, 33, top))
        chars.extend(_chars(date, 57, top))
        chars.extend(_chars(time, 107, top))
        chars.extend(_chars(acct_a, 461, top))
        chars.extend(_chars(name_a, 524, top))
        chars.extend(_chars(summary, 193, top + 7))
        if debit:
            chars.extend(_chars(debit, 322, top + 7))
        if credit:
            chars.extend(_chars(credit, 372, top + 7))
        chars.extend(_chars(balance, 426, top + 7))
        chars.extend(_chars(acct_b, 474, top + 7))
        chars.extend(_chars(name_b, 532, top + 7))

    chars.extend(_chars("第1页", 286, 820))
    return _FakePage(chars=chars, words=words)


def test_grid_reconstructor_builds_logical_rows_from_multiline_ledger():
    table = detect_table_via_grid(_ledger_page())

    assert table is not None
    assert table[0] == [
        "序号",
        "交易日期",
        "交易时间",
        "摘要",
        "凭证种类",
        "借方发生额",
        "贷方发生额",
        "余额",
        "对方账户",
        "对方户名",
    ]
    assert len(table) == 3
    assert table[1] == [
        "1",
        "2022-06-01",
        "16:59:43",
        "往来款",
        "",
        "7,900.00",
        "",
        "18.75",
        "1104010309000388824",
        "镇江小松鼠公司",
    ]
    assert table[2][8] == "70650107360000033"
    assert "第1页" not in "".join(table[2])


def test_bcs_prefers_logical_grid_over_fragmented_physical_rows():
    profile = get_profile("borderless_ledger_bank")
    header = [
        "序号",
        "交易日期",
        "交易时间",
        "摘要",
        "凭证种类",
        "借方发生额",
        "贷方发生额",
        "余额",
        "对方账户",
        "对方户名",
    ]
    logical_rows = [
        [str(i), "2022-06-01", "16:59:43", "摘要", "", "7,900.00", "", "18.75", "1104010309000388824", "户名"]
        for i in range(1, 31)
    ]
    fragmented_rows = []
    for i in range(1, 31):
        fragmented_rows.extend(
            [
                [f"{i} 2022-06-01", "16:59:43", "", "", "", "", "1104010309000户"],
                ["", "", "摘要", "", "7,900.00", "18.75", "388824名"],
                ["", "", "", "", "", "", "公司"],
            ]
        )

    logical = ExtractCandidate(tables=[[header] + logical_rows], layer="grid_reconstructor", confidence=0.89)
    fragmented = ExtractCandidate(
        tables=[
            [
                [
                    "序号交易日期",
                    "交易时间",
                    "摘要",
                    "凭证种类借方发生额",
                    "贷方发生额",
                    "余额",
                    "对方账户对方户名",
                ],
                *fragmented_rows,
            ]
        ],
        layer="x_clustering",
        confidence=0.95,
    )

    pick = pick_best_candidate([fragmented, logical], profile, oracle_rows=30)

    assert pick is not None
    assert pick.candidate.layer == "grid_reconstructor"
