from __future__ import annotations

from docmirror.plugins.alipay_payment.community_plugin import AlipayPaymentPlugin

HEADERS = [
    "收/支",
    "交易对方",
    "商品说明",
    "收/付款方式",
    "金额",
    "交易订单号",
    "商家订单号",
    "交易时间",
]


def _row(direction: str, index: int) -> list[str]:
    return [
        direction,
        f"对方{index}",
        f"说明{index}",
        "余额",
        f"{index}.00",
        f"trade-{index}",
        f"merchant-{index}",
        f"2026-07-{index:02d} 10:00:00",
    ]


def test_alipay_keeps_uncounted_records_and_continuation_table_first_rows() -> None:
    plugin = AlipayPaymentPlugin()
    tables = [
        [
            ["交易时间段：2026-07-01 至 2026-07-31", "", "", "", "", "", "", ""],
            ["交易类型：全部", "", "", "", "", "", "", ""],
            HEADERS,
            _row("收入", 1),
            _row("不计\n收支", 2),
        ],
        [
            _row("不计\n收支", 3),
            _row("支出", 4),
        ],
    ]

    header_row_idx, raw_headers, col_map = plugin._detect_headers(tables)
    transactions = plugin._extract_records(tables, header_row_idx, raw_headers, col_map)
    records = plugin._build_records(transactions)

    assert len(records) == 4
    assert [record["raw"]["收/支"] for record in records] == ["收入", "不计收支", "不计收支", "支出"]
    assert [record["normalized"]["direction"] for record in records] == [
        "income",
        "other",
        "other",
        "expense",
    ]
    assert [record["canonical_raw"]["direction"] for record in records] == [
        "收入",
        "不计收支",
        "不计收支",
        "支出",
    ]
    assert records[0]["canonical_raw"]["amount"] == "1.00"
