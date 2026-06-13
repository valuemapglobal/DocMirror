#!/usr/bin/env python3
"""Generate minimal synthetic PDF fixtures for golden CI smoke tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "synthetic"


def ensure_bank_synthetic() -> Path:
    """3-page bank-style ledger PDF for merge golden smoke."""
    try:
        import fitz
    except ImportError as exc:
        raise SystemExit("PyMuPDF required: pip install docmirror[pdf]") from exc

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "bank_ledger_3page_smoke.pdf"
    if path.exists():
        return path

    doc = fitz.open()
    for page_no in range(3):
        page = doc.new_page()
        if page_no == 0:
            page.insert_text((40, 40), "中国建设银行账户明细信息", fontsize=12)
            page.insert_text((40, 60), "对方户名 借方发生额 贷方发生额", fontsize=10)
        for row in range(5):
            y = 100 + row * 20
            page.insert_text((40, y), f"2024-01-{page_no + 1:02d} row{row} 100.00 200.00", fontsize=9)
    doc.save(str(path))
    doc.close()
    return path


def ensure_credit_synthetic() -> Path:
    """Single-page credit report section-dominant smoke PDF (china-s for CJK fast path)."""
    try:
        import fitz
    except ImportError as exc:
        raise SystemExit("PyMuPDF required") from exc

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "credit_report_section_smoke.pdf"

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    for y, text in [
        (60, "个人信用报告"),
        (90, "一 个人基本信息"),
        (115, "（一）身份信息"),
        (140, "二 信息概要"),
        (165, "（一）信贷交易信息概要"),
        (190, "三 信贷交易信息明细"),
        (215, "（一）非循环贷账户"),
    ]:
        page.insert_text((72, y), text, fontname="china-s", fontsize=11)
    doc.save(str(path))
    doc.close()
    return path


def main() -> int:
    bank = ensure_bank_synthetic()
    credit = ensure_credit_synthetic()
    print(f"generated: {bank}")
    print(f"generated: {credit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
