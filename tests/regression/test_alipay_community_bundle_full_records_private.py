from __future__ import annotations

import asyncio
import csv
import io
import re
from pathlib import Path

import pdfplumber
import pytest

from docmirror.input.entry.factory import PerceiveOptions, perceive_document
from docmirror.input.entry.options import normalize_parse_policy
from docmirror.models.schemas.registry import validate_projection_payload
from docmirror.server.output_builder import build_community_projection, materialize_community_bundle
from scripts.validate.validate_community_artifacts import PAYMENT_DIRECTIONS, payment_direction_cells

pytestmark = [pytest.mark.integration, pytest.mark.slow, pytest.mark.tier_regression]

FIXTURE = Path("tests/fixtures-private/alipay_payment/支付宝账单_支付宝（中国）网络技术有限公司_20230611.pdf")
SOURCE_HEADERS = [
    "direction",
    "counter_party",
    "description",
    "payment_method",
    "amount",
    "trade_no",
    "merchant_no",
    "timestamp",
]
PAYMENT_DIRECTIONS_RAW = {"收入", "支出", "不计收支", "其他"}


def _physical_payment_rows() -> list[tuple[int, dict[str, str]]]:
    rows: list[tuple[int, dict[str, str]]] = []
    with pdfplumber.open(FIXTURE) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            for table in page.extract_tables() or []:
                for cells in table:
                    cells = list(cells)
                    if len(cells) < len(SOURCE_HEADERS):
                        continue
                    values = [str(cell or "").strip().replace("\n", "") for cell in cells]
                    if re.sub(r"\s+", "", values[0]) not in PAYMENT_DIRECTIONS_RAW:
                        continue
                    rows.append((page_number, dict(zip(SOURCE_HEADERS, values, strict=False))))
    return rows


def _without_whitespace(value: object) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def test_alipay_community_json_and_csv_preserve_all_1267_transactions() -> None:
    if not FIXTURE.is_file():
        pytest.skip(f"private fixture unavailable: {FIXTURE}")

    result = asyncio.run(
        perceive_document(
            FIXTURE,
            PerceiveOptions(policy=normalize_parse_policy(enhance_mode="standard", max_pages=50)),
        )
    )
    payload = build_community_projection(result, file_path=str(FIXTURE), document_id="doc_alipay_full")
    assert payload is not None
    read_view = result.to_read_view()
    bundle = materialize_community_bundle(payload, read_view)
    transactions = next(dataset for dataset in payload["datasets"] if dataset["name"] == "transactions")
    csv_content = bundle.render_dataset_csvs()[transactions["csv"]]
    csv_rows = list(csv.DictReader(io.StringIO(csv_content.lstrip("\ufeff"))))
    audit_rows = list(csv.DictReader(io.StringIO(bundle.render_audit_csv().lstrip("\ufeff"))))
    markdown = bundle.render_markdown()
    physical_rows = _physical_payment_rows()

    assert validate_projection_payload("community", payload).valid
    assert len(physical_rows) == 1267
    assert transactions["row_count"] == 1267
    assert len(transactions["rows"]) == 1267
    assert len(csv_rows) == 1267
    assert transactions["completeness"] == {
        "expected_row_count": 1267,
        "emitted_row_count": 1267,
        "omitted_row_count": 0,
        "verified": True,
        "basis": "physical_payment_rows",
    }
    assert [row["record_id"] for row in transactions["rows"]] == [row["record_id"] for row in csv_rows]

    for (source_page, expected), projected, csv_row in zip(
        physical_rows,
        transactions["rows"],
        csv_rows,
        strict=True,
    ):
        assert {key: _without_whitespace(projected["canonical_raw"].get(key)) for key in SOURCE_HEADERS} == {
            key: _without_whitespace(value) for key, value in expected.items()
        }
        assert projected["source"]["page_range"] == [source_page, source_page]
        assert csv_row["_page_start"] == str(source_page)
        assert csv_row["_page_end"] == str(source_page)

    expected_pages = {row["record_id"]: row["source"]["page_range"][0] for row in transactions["rows"]}
    assert audit_rows
    assert all(int(row["page_start"]) == expected_pages[row["record_id"]] for row in audit_rows)
    assert all(int(row["page_end"]) == expected_pages[row["record_id"]] for row in audit_rows)

    directions = [row["normalized"]["direction"] for row in transactions["rows"]]
    assert directions.count("income") == 332
    assert directions.count("expense") == 298
    assert directions.count("other") == 637

    data_cells, header_cells = payment_direction_cells(markdown)
    assert {direction: data_cells[direction] for direction in PAYMENT_DIRECTIONS} == {
        "收入": 332,
        "支出": 298,
        "其他": 0,
        "不计收支": 637,
    }
    assert sum(data_cells[direction] for direction in PAYMENT_DIRECTIONS) == 1267
    assert sum(header_cells[direction] for direction in PAYMENT_DIRECTIONS) == 0

    assert _without_whitespace(csv_rows[0]["description"]) == (
        "【狂欢价】三防热敏标签纸60*40203050708090100x100不干胶条码打印机E邮宝空白彩色"
    )
    assert csv_rows[0]["payment_method"] == "花呗"
    assert csv_rows[43]["trade_no"] == "2023053122001166451408992657_1900462945003447879"
