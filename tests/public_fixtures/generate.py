# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Generate public synthetic fixtures without storing binary documents in Git."""

from __future__ import annotations

import argparse
from pathlib import Path

PUBLIC_FIXTURE_ROOT = Path(__file__).resolve().parent / "generated"


def generate_synthetic_wechat_statement(destination: Path | None = None) -> Path:
    """Create a small, wholly synthetic payment statement for table extraction tests."""
    import fitz

    output = destination or PUBLIC_FIXTURE_ROOT / "wechat_payment" / "synthetic_easy_standard.pdf"
    output.parent.mkdir(parents=True, exist_ok=True)

    document = fitz.open()
    page = document.new_page(width=595.28, height=841.89)
    page.insert_text((190, 48), "WeChat Payment Records", fontname="helv", fontsize=18)
    page.insert_text((235, 75), "Synthetic Transaction History", fontname="helv", fontsize=10)
    for y, text in (
        (115, "User: SYNTHETIC USER"),
        (135, "WeChat ID: synthetic_user_001"),
        (155, "Statement Period: 2025-01-01 to 2025-06-30"),
        (175, "Currency: CNY"),
    ):
        page.insert_text((55, y), text, fontname="helv", fontsize=10)

    column_edges = [40, 130, 285, 365, 455, 555]
    row_edges = [195, 220, 245, 270, 295, 320, 345, 370]
    for x in column_edges:
        page.draw_line((x, row_edges[0]), (x, row_edges[-1]), color=(0, 0, 0), width=0.5)
    for y in row_edges:
        page.draw_line((column_edges[0], y), (column_edges[-1], y), color=(0, 0, 0), width=0.5)

    rows = [
        ["Date", "Transaction", "Amount", "Balance", "Note"],
        ["2025-01-08", "Synthetic Income", "+88.88", "1234.56", "Case A"],
        ["2025-01-20", "Synthetic Taxi", "-35.00", "1199.56", "Case B"],
        ["2025-02-14", "Synthetic Dinner", "-268.00", "931.56", "Case C"],
        ["2025-03-01", "Synthetic Mobile", "-100.00", "831.56", "Case D"],
        ["2025-04-05", "Synthetic Movie", "-60.00", "771.56", "Case E"],
        ["2025-05-01", "Synthetic Transfer", "+500.00", "1271.56", "Case F"],
    ]
    for row_index, row in enumerate(rows):
        y = 211 + row_index * 25
        for column_index, text in enumerate(row):
            page.insert_text((column_edges[column_index] + 3, y), text, fontname="helv", fontsize=8)

    document.set_metadata(
        {
            "title": "DocMirror public synthetic payment fixture",
            "author": "DocMirror contributors",
            "subject": "Synthetic test data only",
            "keywords": "synthetic public fixture",
            "creator": "DocMirror fixture generator",
            "producer": "PyMuPDF",
        }
    )
    document.save(output, garbage=4, deflate=True, clean=True)
    document.close()
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=PUBLIC_FIXTURE_ROOT)
    args = parser.parse_args()
    output = generate_synthetic_wechat_statement(args.output_root / "wechat_payment" / "synthetic_easy_standard.pdf")
    print(f"generated public fixture: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
