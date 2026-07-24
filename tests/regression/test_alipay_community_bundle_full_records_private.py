from __future__ import annotations

import asyncio
import csv
import io
from pathlib import Path

import pytest

from docmirror.input.entry.factory import PerceiveOptions, perceive_document
from docmirror.input.entry.options import normalize_parse_policy
from docmirror.models.schemas.registry import validate_projection_payload
from docmirror.server.output_builder import build_community_projection, materialize_community_bundle
from scripts.validate.validate_community_artifacts import PAYMENT_DIRECTIONS, payment_direction_cells

pytestmark = [pytest.mark.integration, pytest.mark.slow, pytest.mark.tier_regression]

FIXTURE = Path("tests/fixtures-private/alipay_payment/支付宝账单_支付宝（中国）网络技术有限公司_20230611.pdf")


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
    bundle = materialize_community_bundle(payload, result.to_read_view())
    transactions = next(dataset for dataset in payload["datasets"] if dataset["name"] == "transactions")
    csv_content = bundle.render_dataset_csvs()[transactions["csv"]]
    csv_rows = list(csv.DictReader(io.StringIO(csv_content.lstrip("\ufeff"))))
    markdown = bundle.render_markdown()

    assert validate_projection_payload("community", payload).valid
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
