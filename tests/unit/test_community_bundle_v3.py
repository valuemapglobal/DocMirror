from __future__ import annotations

import csv
import io

from docmirror.models.entities.parse_result import (
    CellValue,
    DocumentEntities,
    KeyValuePair,
    PageContent,
    ParseResult,
    RowType,
    TableBlock,
    TableRow,
    TextBlock,
    TextLevel,
)
from docmirror.models.schemas.registry import validate_projection_payload
from docmirror.models.sealed import seal_parse_result
from docmirror.output.community_bundle import project_community_bundle as _project_community_bundle
from docmirror.plugins._base.projector import load_projection_policy

_PROJECTIONS: dict[int, dict] = {}


def project_community_bundle(result, **kwargs):
    projection_data = _PROJECTIONS.get(id(result))
    document_type = str((projection_data or {}).get("document_type") or "generic")
    policy = load_projection_policy(f"docmirror.plugins.{document_type}")
    return _project_community_bundle(
        seal_parse_result(result),
        projection_data=projection_data,
        projection_policy=policy,
        **kwargs,
    )


def _candidate(records: list[dict] | None = None) -> dict:
    return {
        "document": {
            "document_type": "credit_report",
            "document_name": "个人征信.pdf",
            "page_count": 1,
            "language": "zh",
            "properties": {"report_subtype": "personal_detailed"},
        },
        "plugin": {"name": "credit_report"},
        "metadata": {"route_type": "core_domain", "domain_status": "ga"},
        "status": {"success": True, "warnings": [], "errors": []},
        "quality": {"issues": []},
        "data": {
            "fields": {"subject_name": "洪晓鑫"},
            "field_details": {"subject_name": {"raw": "洪晓鑫"}},
            "sections": [{"id": "sec_credit", "title": "信贷记录明细", "source_page_start": 1}],
            "tables": [
                {
                    "id": "table:repayment_records",
                    "section_id": "sec_credit",
                    "data_ref": {"path": "/data/repayment_records"},
                }
            ],
            "repayment_records": records or [],
            "data_dictionary": {
                "fields": {"subject_name": {"label": "姓名", "type": "string"}},
                "datasets": {
                    "repayment_records": {
                        "columns": {
                            "month": {"label": "月份", "type": "string"},
                            "status": {"label": "还款状态", "type": "string"},
                        }
                    }
                },
            },
        },
    }


def _with_projection(result: ParseResult, candidate: dict) -> ParseResult:
    data = candidate["data"]
    fields = dict(data.get("fields") or {})
    datasets: dict[str, list[dict]] = {}
    for key, rows in data.items():
        if not isinstance(rows, list) or not rows or not all(isinstance(row, dict) for row in rows):
            continue
        datasets[key] = [
            {
                **dict(row),
                "record_id": str(row.get("record_id") or f"{key}:r{index:06d}"),
            }
            for index, row in enumerate(rows, start=1)
        ]
    existing_type = str(result.entities.document_type or "")
    _PROJECTIONS[id(result)] = {
        "projector_id": "test-fixture",
        "document_type": existing_type
        if existing_type not in {"", "generic", "unknown"}
        else candidate["document"]["document_type"],
        "entity_fields": {"subject_name": fields["subject_name"]} if fields.get("subject_name") else {},
        "domain_facts": {
            **candidate["document"].get("properties", {}),
            **fields,
            "field_details": data.get("field_details", {}),
            "data_dictionary": data.get("data_dictionary", {}),
        },
        "datasets": datasets,
        "sections": tuple(data.get("sections") or ()),
    }
    return result


def test_public_json_has_exact_six_blocks_and_complete_dataset_rows() -> None:
    records = [{"repayment_id": f"rep_{i}", "month": f"2025-{i:02d}", "status": "N"} for i in range(1, 13)]
    result = _with_projection(
        ParseResult(entities=DocumentEntities(document_type="credit_report")),
        _candidate(records),
    )
    bundle = project_community_bundle(result, file_id="001", document_id="doc_test")
    payload = bundle.json_payload()

    assert set(payload) == {"schema", "document", "sections", "datasets", "files", "warnings"}
    assert payload["schema"]["version"] == "3.0.0"
    assert payload["schema"]["domain"] == "personal_credit_report_detailed"
    assert payload["datasets"][0]["row_count"] == 12
    assert len(payload["datasets"][0]["rows"]) == 12
    assert payload["datasets"][0]["primary_key"] == "record_id"
    assert payload["datasets"][0]["completeness"] == {
        "expected_row_count": 12,
        "emitted_row_count": 12,
        "omitted_row_count": 0,
        "verified": True,
        "basis": "canonical_dataset",
    }
    assert [row["record_id"] for row in payload["datasets"][0]["rows"]] == [
        f"repayment_records:r{index:06d}" for index in range(1, 13)
    ]
    assert payload["datasets"][0]["rows"][0]["normalized"]["month"] == "2025-01"
    assert validate_projection_payload("community", payload).valid


def test_markdown_contains_every_physical_table_row_without_preview_limit() -> None:
    rows = [
        TableRow(cells=[CellValue(text=str(index)), CellValue(text=f"状态{index}")], row_type=RowType.DATA)
        for index in range(1, 177)
    ]
    rows.append(TableRow(cells=[CellValue(text="合计"), CellValue(text="176")], row_type=RowType.SUMMARY))
    result = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                texts=[TextBlock(content="个人信用报告", level=TextLevel.TITLE, bbox=[0, 0, 100, 10])],
                key_values=[KeyValuePair(key="姓名", value="洪晓鑫", bbox=[0, 12, 100, 20])],
                tables=[TableBlock(headers=["序号", "还款状态"], rows=rows, bbox=[0, 30, 100, 700])],
            )
        ],
        entities=DocumentEntities(document_type="credit_report"),
    )
    _with_projection(result, _candidate())
    bundle = project_community_bundle(result, document_id="doc_test")
    markdown = bundle.render_markdown()

    assert "# 个人信用报告" in markdown
    assert "**姓名:** 洪晓鑫" in markdown
    for index in range(1, 177):
        assert f"| {index} | 状态{index} |" in markdown
    assert "| 合计 | 176 |" in markdown


def test_dataset_bundle_has_one_wide_row_per_record_and_cell_audit() -> None:
    records = [
        {
            "repayment_id": f"rep_{index}",
            "account_id": "shared_account",
            "normalized": {"month": f"2025-{index:02d}", "status": "N"},
            "raw": {"month": f"2025-{index:02d}", "status": "N"},
        }
        for index in range(1, 13)
    ]
    result = _with_projection(
        ParseResult(entities=DocumentEntities(document_type="credit_report")),
        _candidate(records),
    )
    bundle = project_community_bundle(result, document_id="doc_test")
    dataset_csvs = bundle.render_dataset_csvs()
    rows = list(csv.DictReader(io.StringIO(dataset_csvs["001_datasets/repayment_records.csv"].lstrip("\ufeff"))))
    audit_rows = list(csv.DictReader(io.StringIO(bundle.render_audit_csv().lstrip("\ufeff"))))

    assert len(rows) == 12
    assert len({row["record_id"] for row in rows}) == 12
    assert list(rows[0]) == ["record_id", "_page_start", "_page_end", "month", "status"]
    assert rows[0]["month"] == "2025-01"
    assert len(audit_rows) == 24
    assert {row["dataset_id"] for row in audit_rows} == {"ds_repayment_records"}
    assert "subject_name" not in {row["field_key"] for row in audit_rows}


def test_csv_preserves_signed_numbers_but_neutralizes_text_formulas() -> None:
    candidate = _candidate(
        [
            {
                "repayment_id": "rep_1",
                "normalized": {"amount": "-10.25", "status": "=CMD()"},
                "raw": {"amount": "-10.25", "status": "=CMD()"},
            }
        ]
    )
    candidate["data"]["data_dictionary"]["datasets"]["repayment_records"]["columns"]["amount"] = {
        "label": "金额",
        "type": "money",
    }
    result = _with_projection(ParseResult(entities=DocumentEntities(document_type="credit_report")), candidate)
    bundle = project_community_bundle(result, document_id="doc_test")
    rows = list(
        csv.DictReader(io.StringIO(bundle.render_dataset_csvs()["001_datasets/repayment_records.csv"].lstrip("\ufeff")))
    )
    audit_rows = list(csv.DictReader(io.StringIO(bundle.render_audit_csv().lstrip("\ufeff"))))

    assert rows[0]["amount"] == "-10.25"
    assert rows[0]["status"] == "'=CMD()"
    amount = next(row for row in audit_rows if row["field_key"] == "amount")
    status = next(row for row in audit_rows if row["field_key"] == "status")
    assert amount["value"] == "-10.25"
    assert amount["raw"] == "-10.25"
    assert amount["csv_escape_applied"] == "false"
    assert status["value"] == "'=CMD()"
    assert status["raw"] == "'=CMD()"
    assert status["csv_escape_applied"] == "true"


def test_audit_uses_canonical_field_keys_with_original_source_values() -> None:
    candidate = _candidate(
        [
            {
                "normalized": {"direction": "expense", "amount": "35.00"},
                "raw": {"收/支": "支出", "金额": "35.00"},
                "canonical_raw": {"direction": "支出", "amount": "35.00"},
            }
        ]
    )
    candidate["data"]["data_dictionary"]["datasets"]["repayment_records"]["columns"] = {
        "direction": {"label": "收/支", "type": "enum"},
        "amount": {"label": "金额", "type": "money"},
    }
    result = _with_projection(ParseResult(entities=DocumentEntities(document_type="credit_report")), candidate)
    bundle = project_community_bundle(result, document_id="doc_test")

    wide_rows = list(
        csv.DictReader(io.StringIO(bundle.render_dataset_csvs()["001_datasets/repayment_records.csv"].lstrip("\ufeff")))
    )
    audit_rows = list(csv.DictReader(io.StringIO(bundle.render_audit_csv().lstrip("\ufeff"))))

    assert list(wide_rows[0]) == ["record_id", "_page_start", "_page_end", "amount", "direction"]
    direction = next(row for row in audit_rows if row["field_key"] == "direction")
    assert direction["value"] == "expense"
    assert direction["raw"] == "支出"
    assert {row["field_key"] for row in audit_rows} == {"direction", "amount"}


def test_different_logical_datasets_are_written_to_different_wide_csvs() -> None:
    candidate = _candidate([{"month": "2025-01", "status": "N"}])
    candidate["data"]["inquiry_records"] = [{"query_date": "2025-02-01", "institution": "银行"}]
    candidate["data"]["data_dictionary"]["datasets"]["inquiry_records"] = {
        "columns": {
            "query_date": {"label": "查询日期", "type": "date"},
            "institution": {"label": "查询机构", "type": "string"},
        }
    }
    result = _with_projection(ParseResult(entities=DocumentEntities(document_type="credit_report")), candidate)
    bundle = project_community_bundle(result, document_id="doc_test")

    csvs = bundle.render_dataset_csvs()

    assert set(csvs) == {
        "001_datasets/repayment_records.csv",
        "001_datasets/inquiry_records.csv",
    }
    repayment_header = next(csv.reader(io.StringIO(csvs["001_datasets/repayment_records.csv"].lstrip("\ufeff"))))
    inquiry_header = next(csv.reader(io.StringIO(csvs["001_datasets/inquiry_records.csv"].lstrip("\ufeff"))))
    assert repayment_header == ["record_id", "_page_start", "_page_end", "month", "status"]
    assert inquiry_header == ["record_id", "_page_start", "_page_end", "institution", "query_date"]


def test_payment_records_use_transaction_business_name() -> None:
    candidate = _candidate([{"normalized": {"amount": "10.00"}, "raw": {"amount": "10.00"}}])
    candidate["data"]["records"] = candidate["data"].pop("repayment_records")
    candidate["data"]["data_dictionary"]["record_columns"] = {"amount": {"label": "金额", "type": "money"}}
    result = _with_projection(ParseResult(entities=DocumentEntities(document_type="alipay_payment")), candidate)
    bundle = project_community_bundle(result, document_id="doc_test")

    assert bundle.datasets[0].public["id"] == "ds_transactions"
    assert bundle.datasets[0].public["name"] == "transactions"
    assert bundle.datasets[0].public["type"] == "transaction"
    assert bundle.datasets[0].public["csv"] == "001_datasets/transactions.csv"


def test_markdown_escapes_table_delimiters_but_preserves_content() -> None:
    result = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                tables=[
                    TableBlock(
                        headers=["内容"],
                        rows=[TableRow(cells=[CellValue(text="A|B\nC")])],
                    )
                ],
            )
        ]
    )
    _with_projection(result, _candidate())
    markdown = project_community_bundle(result, document_id="doc_test").render_markdown()
    assert "A\\|B C" in markdown
    assert "<br>" not in markdown


def test_markdown_renders_payment_record_promoted_to_header_as_data() -> None:
    result = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                tables=[
                    TableBlock(
                        headers=["不计\n收支", "第一条交易"],
                        rows=[TableRow(cells=[CellValue(text="收入"), CellValue(text="第二条交易")])],
                    )
                ],
            )
        ]
    )
    markdown = project_community_bundle(result, document_id="doc_payment_header").render_markdown()

    assert "| 不计收支 | 第一条交易 |" in markdown
    assert "| 收入 | 第二条交易 |" in markdown
    assert "<table>" not in markdown


def test_markdown_image_omission_adds_idempotent_info_warning() -> None:
    result = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                texts=[TextBlock(content='<div><img src="imgs/missing.jpg" alt="Image" /></div>')],
            )
        ]
    )
    _with_projection(result, _candidate())
    bundle = project_community_bundle(result, document_id="doc_test")

    first = bundle.render_markdown()
    second = bundle.render_markdown()
    warnings = [warning for warning in bundle.json_payload()["warnings"] if warning["code"] == "MARKDOWN_IMAGE_OMITTED"]

    assert first == second
    assert "<img" not in first
    assert warnings == [
        {
            "code": "MARKDOWN_IMAGE_OMITTED",
            "level": "info",
            "message": "Unmaterialized source images were omitted from content Markdown.",
        }
    ]


def test_large_dataset_is_not_truncated_and_json_csv_ids_match() -> None:
    records = [
        {
            "record_id": f"repayment:{index:06d}",
            "normalized": {"month": f"2025-{((index - 1) % 12) + 1:02d}", "status": "N"},
            "raw": {"month": f"2025-{((index - 1) % 12) + 1:02d}", "status": "N"},
        }
        for index in range(1, 5001)
    ]
    result = _with_projection(
        ParseResult(entities=DocumentEntities(document_type="credit_report")),
        _candidate(records),
    )
    bundle = project_community_bundle(result, document_id="doc_large")

    payload = bundle.json_payload()
    dataset = payload["datasets"][0]
    csvs = bundle.render_dataset_csvs()
    csv_rows = list(csv.DictReader(io.StringIO(csvs["001_datasets/repayment_records.csv"].lstrip("\ufeff"))))

    assert dataset["row_count"] == 5000
    assert len(dataset["rows"]) == 5000
    assert dataset["rows"][-1]["record_id"] == "repayment:005000"
    assert [row["record_id"] for row in dataset["rows"]] == [row["record_id"] for row in csv_rows]
    assert bundle.conservation_issues(payload=payload, dataset_csvs=csvs) == []


def test_conservation_gate_rejects_json_or_csv_row_loss() -> None:
    records = [{"month": f"2025-{index:02d}", "status": "N"} for index in range(1, 4)]
    result = _with_projection(
        ParseResult(entities=DocumentEntities(document_type="credit_report")),
        _candidate(records),
    )
    bundle = project_community_bundle(result, document_id="doc_gate")
    payload = bundle.json_payload()
    csvs = bundle.render_dataset_csvs()

    payload["datasets"][0]["rows"].pop()
    assert any(":row_count=" in issue for issue in bundle.conservation_issues(payload=payload))

    intact_payload = bundle.json_payload()
    csv_lines = csvs["001_datasets/repayment_records.csv"].splitlines(keepends=True)
    truncated_csvs = dict(csvs)
    truncated_csvs["001_datasets/repayment_records.csv"] = "".join(csv_lines[:-1])
    assert any(
        ":csv=" in issue for issue in bundle.conservation_issues(payload=intact_payload, dataset_csvs=truncated_csvs)
    )
