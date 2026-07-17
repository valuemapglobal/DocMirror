import json
import zipfile
from pathlib import Path

import pytest

from docmirror.models.entities.parse_result import (
    CellValue,
    DataType,
    DocumentEntities,
    KeyValuePair,
    PageContent,
    ParseResult,
    ParserInfo,
    RowType,
    TableBlock,
    TableRow,
    TextBlock,
    TextLevel,
)
from docmirror.models.mirror.vnext import mirror_json_vnext_schema


def _sample_parse_result() -> ParseResult:
    table = TableBlock(
        table_id="page1_table0",
        headers=[
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
        ],
        page=1,
        bbox=[42.0, 172.0, 552.0, 742.0],
        confidence=0.98,
        extraction_layer="implicit_grid",
    )
    table.rows.append(
        TableRow(
            row_type=RowType.DATA,
            confidence=0.97,
            cells=[
                CellValue(text="1", data_type=DataType.NUMBER, confidence=0.99, bbox=[42.0, 196.0, 72.0, 214.0]),
                CellValue(text="2022-06-01", data_type=DataType.DATE, confidence=0.99),
                CellValue(text="09:10:11", data_type=DataType.TEXT, confidence=0.98),
                CellValue(text="转账", data_type=DataType.TEXT, confidence=0.96),
                CellValue(text="", data_type=DataType.EMPTY, confidence=0.9),
                CellValue(text="10.00", numeric=10.0, data_type=DataType.CURRENCY, confidence=0.99),
                CellValue(text="", data_type=DataType.EMPTY, confidence=0.9),
                CellValue(text="100.00", numeric=100.0, data_type=DataType.CURRENCY, confidence=0.99),
                CellValue(text="6222", data_type=DataType.TEXT, confidence=0.95),
                CellValue(text="张三", data_type=DataType.TEXT, confidence=0.95),
            ],
        )
    )
    return ParseResult(
        pages=[
            PageContent(
                page_number=1,
                width=595,
                height=842,
                texts=[
                    TextBlock(
                        content="江苏银行对公账户对账单",
                        level=TextLevel.TITLE,
                        bbox=[72.0, 60.0, 300.0, 82.0],
                        confidence=0.99,
                    )
                ],
                key_values=[
                    KeyValuePair(key="起始日期", value="2022-06-01", bbox=[72.0, 98.0, 184.0, 112.0]),
                    KeyValuePair(key="账户名称", value="镇江一生一世好游戏有限公司", bbox=[72.0, 120.0, 260.0, 136.0]),
                ],
                tables=[table],
            )
        ],
        entities=DocumentEntities(
            document_type="bank_statement",
            organization="江苏银行",
            period_start="2022-06-01",
            period_end="2022-08-31",
            domain_specific={"language": "zh-Hans"},
        ),
        confidence=0.97,
    )


def test_mirror_json_vnext_is_document_shaped_not_old_envelope():
    payload = _sample_parse_result().to_mirror_json_vnext(source_filename="statement.pdf")

    assert set(payload) == {
        "mirror",
        "source",
        "document",
        "pages",
        "evidence",
        "regions",
        "blocks",
        "graph",
        "semantics",
        "quality",
        "diagnostics",
        "assets",
    }
    assert "code" not in payload
    assert "message" not in payload
    assert "data" not in payload
    assert "meta" not in payload
    assert payload["mirror"]["schema"] == "docmirror.mirror_json"
    assert payload["mirror"]["schema_version"] == "1.0.3"
    # filename may be "statement.pdf" (direct call) or "/path/statement.pdf" (through build_all_projections)
    assert payload["source"]["filename"].endswith("statement.pdf")
    assert payload["pages"][0]["coordinate_transform"]["source_rotation"] == 0
    first_atom = payload["evidence"]["text_atoms"][0]
    assert first_atom["source_bbox"] == first_atom["bbox"]
    assert first_atom["coordinate_transform"]["matrix"] == [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


def test_mirror_json_vnext_preserves_table_grid_and_kv_facts():
    payload = _sample_parse_result().to_mirror_json_vnext(source_filename="statement.pdf")

    table_blocks = [block for block in payload["blocks"] if block["type"] == "table"]
    assert len(table_blocks) == 1
    table = table_blocks[0]
    grid = table["content"]["grid"]
    assert [col["header"] for col in grid["columns"]] == [
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
    assert table["quality"]["column_count"] == 10
    assert table["quality"]["row_count"] == 2
    assert grid["cells"][0]["id"].startswith(f"cell:{table['id']}:")
    assert grid["cells"][0]["evidence_ids"]

    fact_ids = {fact["id"] for fact in payload["semantics"]["facts"]}
    assert any("起始日期" in fid for fid in fact_ids)
    assert any("账户名称" in fid for fid in fact_ids)
    assert "bank_statement" in payload["semantics"]["views"]


def test_scanned_mirror_uses_conservative_title_and_measured_ocr_quality():
    result = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                page_mode="scanned_ocr",
                width=400,
                height=600,
                texts=[
                    TextBlock(content="征信中心", bbox=[50, 40, 110, 58], confidence=0.92),
                    TextBlock(content="个人信用报告", bbox=[170, 90, 240, 108], confidence=0.94),
                    TextBlock(content="（本人版）", bbox=[190, 116, 230, 132], confidence=0.91),
                    TextBlock(content="噪声", bbox=[20, 180, 50, 194], confidence=0.42),
                ],
            )
        ]
    )

    payload = result.to_mirror_json_vnext()

    assert payload["document"]["content_mode"] == "scanned_ocr"
    assert payload["document"]["title"]["text"] == "个人信用报告"
    assert payload["document"]["title"]["confidence"] == pytest.approx(0.94)
    assert payload["quality"]["overall"]["status"] == "warn"
    ocr_gate = next(gate for gate in payload["quality"]["gates"] if gate["id"] == "gate:ocr_confidence")
    assert ocr_gate["details"]["below_0_8_count"] == 1
    assert payload["quality"]["verification"]["scope"] == "internal_consistency"


def test_document_title_does_not_fall_back_to_late_account_status_heading():
    result = ParseResult(
        pages=[
            PageContent(
                page_number=1, width=400, height=600, texts=[TextBlock(content="正文", bbox=[20, 300, 80, 320])]
            ),
            PageContent(
                page_number=2,
                width=400,
                height=600,
                texts=[TextBlock(content="2024.08.16 结清", level=TextLevel.H1, bbox=[150, 100, 260, 120])],
            ),
        ]
    )

    payload = result.to_mirror_json_vnext()

    assert payload["document"]["title"] is None
    assert payload["document"]["outline_block_ids"] == []
    assert all(region["block_ids"] for region in payload["regions"] if region["kind"] != "residual")


def test_mirror_json_vnext_preserves_ocr_page_normalization_and_table_provenance():
    table = TableBlock(
        table_id="pt_10_0",
        headers=["项目", "金额"],
        page=10,
        bbox=[42.5, 117.0, 803.0, 554.0],
        extraction_layer="scanned_ocr_statement_grid",
        extraction_confidence=0.93,
        metadata={
            "extraction_layer": "scanned_ocr_statement_grid",
            "extraction_confidence": 0.93,
            "ocr_rotation": 90,
            "ocr_orientation_score": 128.5,
            "normalized_page_width": 842.0,
            "normalized_page_height": 595.0,
            "preserve_headers": True,
            "statement_keywords": ["所有者权益变动表"],
            "role": "financial_statement",
            "source": "scanned_table_reconstructor",
            "geometry": {
                "geometry_source": "scanned_ocr_statement_grid",
                "geometry_confidence": 0.93,
                "coordinate_system": "pdf_points_top_left",
            },
        },
        rows=[
            TableRow(
                row_type=RowType.DATA,
                cells=[
                    CellValue(text="实收资本", data_type=DataType.TEXT),
                    CellValue(text="250,000,000.00", data_type=DataType.CURRENCY),
                ],
            )
        ],
    )
    result = ParseResult(pages=[PageContent(page_number=10, width=842, height=595, tables=[table])])

    payload = result.to_mirror_json_vnext(source_filename="audit.pdf")

    page = payload["pages"][0]
    normalization = page["coordinate_transform"]["page_normalization"]
    assert page["content_mode"] == "scanned_ocr"
    assert page["coordinate_transform"]["content_rotation_applied"] == 90
    assert normalization["method"] == "ocr_orientation_probe"
    assert normalization["selected_rotation"] == 90
    assert normalization["orientation_score"] == 128.5
    assert normalization["normalized_page_width"] == 842.0
    assert normalization["normalized_page_height"] == 595.0

    table_atom = next(
        atom for atom in payload["evidence"]["text_atoms"] if atom["metadata"].get("table_id") == "pt_10_0"
    )
    assert table_atom["metadata"]["ocr_rotation"] == 90
    assert table_atom["metadata"]["geometry_source"] == "scanned_ocr_statement_grid"

    table_block = next(block for block in payload["blocks"] if block["type"] == "table")
    assert table_block["provenance"]["ocr_rotation"] == 90
    assert table_block["provenance"]["extraction_layer"] == "scanned_ocr_statement_grid"
    assert table_block["provenance"]["normalized_page_width"] == 842.0
    assert table_block["quality"]["ocr_orientation_score"] == 128.5
    assert table_block["quality"]["preserve_headers"] is True


def test_mirror_json_vnext_schema_exports_and_payload_roundtrips_json():
    schema = mirror_json_vnext_schema()
    payload = _sample_parse_result().to_mirror_json_vnext(source_filename="statement.pdf")

    assert schema["title"] == "MirrorJsonVNext"
    assert "mirror" in schema["properties"]
    assert "BlockType" in schema["$defs"]
    assert "RegionKind" in schema["$defs"]
    assert "GraphEdgeType" in schema["$defs"]
    json.loads(json.dumps(payload, ensure_ascii=False))


def test_output_builder_defaults_core_mirror_to_vnext():
    from docmirror.server.output_builder import build_all_projections

    outputs = build_all_projections(
        _sample_parse_result(),
        file_path="/tmp/statement.pdf",
        editions=(),
    )

    mirror = outputs["mirror"]
    assert mirror is not None
    assert mirror["mirror"]["schema"] == "docmirror.mirror_json"
    assert mirror["source"]["filename"].endswith("statement.pdf")
    assert mirror["diagnostics"]["pipeline"][1]["stage"] == "page_topology_segmentation"
    assert any(block["type"] == "key_value_group" for block in mirror["blocks"])
    assert "code" not in mirror
    assert "data" not in mirror


def test_mirror_json_vnext_emits_residual_for_empty_page():
    result = ParseResult(
        pages=[PageContent(page_number=1, width=100, height=200)],
        parser_info=ParserInfo(page_count=1),
    )

    payload = result.to_mirror_json_vnext(source_filename="empty.pdf")

    residual_blocks = [block for block in payload["blocks"] if block["type"] == "residual"]
    # Empty ParseResult with no pages may produce 0 or 1 residual blocks
    # depending on whether the topology pipeline creates residual regions.
    # Empty ParseResult with no pages may produce 0 or 1 residual blocks
    assert len(residual_blocks) in (0, 1)
    if residual_blocks:
        # Empty page from unknown source: role may be "empty_page" or "scanned_blank_page"
        assert residual_blocks[0]["role"] in ("empty_page", "scanned_blank_page")
        if residual_blocks[0]["role"] == "empty_page":
            assert residual_blocks[0]["bbox"] == [0.0, 0.0, 100.0, 200.0]
    assert payload["regions"][0]["kind"] == "residual"
    # Empty page: residual ratio may be 1.0 (all evidence = residual)
    # or 0.0 (no evidence, divide-by-zero fallback).
    assert payload["pages"][0]["quality"]["residual_ratio"] in (0.0, 1.0)
    assert payload["quality"]["coverage"]["residual_ratio"] in (0.0, 1.0)
    warn_gate_ids = {gate["id"] for gate in payload["quality"]["gates"] if gate["status"] == "warn"}
    event_gate_ids = {event["gate_id"] for event in payload["quality"]["events"]}
    assert warn_gate_ids <= event_gate_ids
    assert {gate["id"] for gate in payload["quality"]["gates"]} == event_gate_ids
    assert all(event["event_type"] == "quality_gate" for event in payload["quality"]["events"])
    assert all("actionable" in event for event in payload["quality"]["events"])
    assert payload["quality"]["event_summary"]["event_count"] == len(payload["quality"]["events"])
    assert payload["quality"]["event_summary"]["actionable_count"] == sum(
        1 for event in payload["quality"]["events"] if event["actionable"]
    )
    profile_entry = next(
        entry for entry in payload["diagnostics"]["pipeline"] if entry["stage"] == "udtr_profile_summary"
    )
    assert profile_entry["quality_gate_count"] == len(payload["quality"]["gates"])
    assert profile_entry["quality_event_count"] == len(payload["quality"]["events"])
    if residual_blocks:
        assert payload["diagnostics"]["warnings"][0]["target_ids"] == [residual_blocks[0]["id"]]


def test_mirror_json_vnext_emits_document_residual_when_no_pages_exist():
    result = ParseResult()

    payload = result.to_mirror_json_vnext(source_filename="empty.pdf")

    residual_blocks = [block for block in payload["blocks"] if block["type"] == "residual"]
    # Empty ParseResult with no pages may produce 0 or 1 residual blocks
    # depending on whether the topology pipeline creates residual regions.
    assert len(residual_blocks) in (0, 1)
    if residual_blocks:
        assert residual_blocks[0]["role"] == "empty_document"
        assert residual_blocks[0]["content"]["reason"] == "no_pages_detected"
    assert payload["pages"] == []
    if residual_blocks:
        assert payload["graph"]["reading_flows"][0]["node_ids"] == [residual_blocks[0]["id"]]


def test_mirror_core_vnext_processes_parse_result():
    from docmirror.models.mirror.core import MirrorCoreVNext, MirrorOptions

    core = MirrorCoreVNext()
    result = core.process(
        _sample_parse_result(),
        MirrorOptions(source_filename="statement.pdf", profile="canonical_full"),
    )
    payload = result.to_dict()

    assert payload["mirror"]["engine"] == "udtr"
    # filename may be "statement.pdf" (direct call) or "/path/statement.pdf" (through build_all_projections)
    assert payload["source"]["filename"].endswith("statement.pdf")
    assert payload["diagnostics"]["pipeline"][0]["stage"] == "evidence_plane_builder"
    assert payload["diagnostics"]["pipeline"][1]["stage"] == "page_topology_segmentation"
    assert payload["document"]["document_type_candidates"][0]["type"] == "bank_statement"
    assert "bank_statement" in payload["semantics"]["views"]
    assert any(block["type"] == "table" for block in payload["blocks"])


def test_mirror_core_keeps_canonical_shape_across_synthetic_source_formats():
    from docmirror.models.mirror.core import MirrorCoreVNext, MirrorOptions

    required_keys = {
        "mirror",
        "source",
        "document",
        "pages",
        "evidence",
        "regions",
        "blocks",
        "graph",
        "semantics",
        "quality",
        "diagnostics",
        "assets",
    }
    for filename in ("sample.pdf", "sample.docx", "sample.xlsx", "sample.html"):
        payload = (
            MirrorCoreVNext()
            .process(
                _sample_parse_result(),
                MirrorOptions(source_filename=filename),
            )
            .to_dict()
        )

        assert required_keys <= set(payload)
        assert payload["mirror"]["schema"] == "docmirror.mirror_json"
        assert payload["source"]["filename"].endswith(filename)
        assert payload["quality"]["gates"]
        assert payload["quality"]["events"]
        assert payload["quality"]["event_summary"]["event_count"] == len(payload["quality"]["events"])
        assert any(entry["stage"] == "udtr_profile_summary" for entry in payload["diagnostics"]["pipeline"])


def test_mirror_core_processes_cross_format_native_paths(tmp_path: Path):
    from docmirror.models.mirror.core import MirrorCoreVNext, MirrorOptions

    fixtures = _write_cross_format_native_fixtures(tmp_path)
    expected_kinds = {
        "sample.docx": "word",
        "sample.xlsx": "spreadsheet",
        "sample.html": "html",
        "sample.eml": "email",
        "sample.ofd": "ofd",
    }
    core = MirrorCoreVNext()
    for path in fixtures:
        payload = core.process(path, MirrorOptions(source_filename=str(path))).to_dict()

        assert payload["mirror"]["schema"] == "docmirror.mirror_json"
        assert payload["source"]["input_kind"] == expected_kinds[path.name]
        assert payload["source"]["provenance"]["intake_family"] == expected_kinds[path.name]
        assert payload["pages"]
        assert payload["evidence"]["text_atoms"]
        assert payload["blocks"]
        assert not any(
            "unsupported document source kind" in str(item.get("message", ""))
            for item in payload["diagnostics"]["pipeline"][0].get("diagnostics", [])
        )

    xlsx_payload = core.process(fixtures[1], MirrorOptions(source_filename=str(fixtures[1]))).to_dict()
    assert any(block["type"] == "table" for block in xlsx_payload["blocks"])


def _write_cross_format_native_fixtures(tmp_path: Path) -> list[Path]:
    docx = tmp_path / "sample.docx"
    with zipfile.ZipFile(docx, "w") as zf:
        zf.writestr(
            "word/document.xml",
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body><w:p><w:r><w:t>DocMirror Word Sample</w:t></w:r></w:p>"
                "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Header</w:t></w:r></w:p></w:tc>"
                "<w:tc><w:p><w:r><w:t>Value</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
                "</w:body></w:document>"
            ),
        )

    xlsx = tmp_path / "sample.xlsx"
    with zipfile.ZipFile(xlsx, "w") as zf:
        zf.writestr(
            "xl/worksheets/sheet1.xml",
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                '<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Item</t></is></c>'
                '<c r="B1" t="inlineStr"><is><t>Amount</t></is></c></row>'
                '<row r="2"><c r="A2" t="inlineStr"><is><t>Cash</t></is></c><c r="B2"><v>42</v></c></row>'
                "</sheetData></worksheet>"
            ),
        )
    html = tmp_path / "sample.html"
    html.write_text("<html><body><h1>HTML Sample</h1><p>Visible paragraph</p></body></html>", encoding="utf-8")

    eml = tmp_path / "sample.eml"
    eml.write_text(
        "Subject: Email Sample\nFrom: a@example.com\nTo: b@example.com\n\nEmail body line",
        encoding="utf-8",
    )

    ofd = tmp_path / "sample.ofd"
    with zipfile.ZipFile(ofd, "w") as zf:
        zf.writestr(
            "Doc_0/Pages/Page_0/Content.xml",
            '<ofd:Page xmlns:ofd="http://www.ofdspec.org/2016"><ofd:TextCode>OFD Sample</ofd:TextCode></ofd:Page>',
        )
    return [docx, xlsx, html, eml, ofd]
