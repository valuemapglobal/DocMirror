import pytest

from docmirror.input.canonical import assemble_parse_result
from docmirror.input.extraction.scanned_table_reconstructor import (
    reconstruct_scanned_bordered_tables,
    reconstruct_scanned_statement_table,
)
from docmirror.models.entities.domain import Block, PageLayout
from docmirror.models.sealed import seal_parse_result
from docmirror.output.mirror_projector import project_mirror


def _ocr_block(text: str, x0: float, y0: float, x1: float, y1: float, idx: int) -> Block:
    block_id = f"ocr:p0001:{idx:04d}"
    return Block(
        block_id=block_id,
        block_type="text",
        bbox=(x0, y0, x1, y1),
        page=1,
        raw_content=text,
        attrs={
            "ocr_source": "rapidocr_pdf_page",
            "confidence": 0.95,
            "ocr_rotation": 90,
            "ocr_orientation_score": 42.5,
            "normalized_page_width": 842.0,
            "normalized_page_height": 595.0,
        },
        evidence_ids=(block_id,),
    )


def test_reconstruct_scanned_statement_table_from_ocr_tokens():
    rows = [
        ["合并资产负债表", "", "", ""],
        ["项", "目", "年末余额", "年初余额"],
        ["货币资金", "", "144,830,970.96", "116,950,772.82"],
        ["应收账款", "", "474,699,684.24", "415,024,578.41"],
        ["资产总计", "", "1,741,575,059.55", "1,634,837,000.55"],
    ]
    blocks = []
    idx = 0
    for row_idx, row in enumerate(rows):
        y0 = 80 + row_idx * 28
        for col_idx, text in enumerate(row):
            if not text:
                continue
            x0 = 72 + col_idx * 135
            blocks.append(_ocr_block(text, x0, y0, x0 + 92, y0 + 14, idx))
            idx += 1

    table = reconstruct_scanned_statement_table(
        blocks,
        page_number=1,
        page_width=595,
        page_height=842,
    )

    assert table is not None
    assert table.block_type == "table"
    assert table.raw_content[0] == ["项目", "年末余额", "年初余额"]
    assert any("144,830,970.96" in row for row in table.raw_content)
    assert table.attrs["extraction_layer"] == "scanned_ocr_statement_grid"
    assert table.attrs["ocr_rotation"] == 90
    assert table.attrs["ocr_orientation_score"] == 42.5
    assert table.attrs["normalized_page_width"] == 842.0
    assert table.attrs["normalized_page_height"] == 595.0
    assert table.attrs["geometry"]["cell_bboxes"][1][0] is not None
    assert table.attrs["geometry"]["cell_evidence_ids"][1][0]


def test_reconstruct_scanned_statement_table_rejects_low_signal_noise():
    blocks = [_ocr_block("0", 100 + i * 10, 100 + i * 20, 105 + i * 10, 110 + i * 20, i) for i in range(12)]

    table = reconstruct_scanned_statement_table(
        blocks,
        page_number=1,
        page_width=595,
        page_height=842,
    )

    assert table is None


def test_reconstruct_scanned_bordered_tables_preserves_multiple_physical_grids():
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    image = np.full((600, 400, 3), 255, dtype=np.uint8)
    for y in (50, 100, 150, 200):
        cv2.line(image, (20, y), (380, y), (0, 0, 0), 2)
    for x in (20, 140, 260, 380):
        cv2.line(image, (x, 50), (x, 200), (0, 0, 0), 2)
    for y in (300, 350, 400):
        cv2.line(image, (30, y), (370, y), (0, 0, 0), 2)
    for x in (30, 200, 370):
        cv2.line(image, (x, 300), (x, 400), (0, 0, 0), 2)

    values = [
        ("A", 30, 60),
        ("B", 150, 60),
        ("C", 270, 60),
        ("D", 30, 110),
        ("E", 40, 310),
        ("F", 220, 310),
        ("G", 40, 360),
    ]
    blocks = [_ocr_block(text, x, y, x + 50, y + 20, index) for index, (text, x, y) in enumerate(values)]

    tables = reconstruct_scanned_bordered_tables(
        image,
        blocks,
        page_number=1,
        page_width=400,
        page_height=600,
    )

    assert len(tables) == 2
    assert tables[0].attrs["extraction_layer"] == "scanned_image_line_grid"
    assert tables[0].attrs["preserve_headers"] is False
    assert tables[0].raw_content[0] == ["A", "B", "C"]
    assert tables[1].raw_content[0] == ["E", "F"]
    assert tables[0].attrs["geometry"]["cell_bboxes"][0][0]
    assert tables[0].attrs["geometry"]["cell_evidence_ids"][0][0]


def test_reconstruct_scanned_bordered_table_restores_open_outer_columns():
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    image = np.full((260, 400, 3), 255, dtype=np.uint8)
    for y in (30, 100, 170):
        cv2.line(image, (20, y), (380, y), (0, 0, 0), 2)
    # Financial-note tables commonly omit their left and right vertical rules.
    for x in (140, 260):
        cv2.line(image, (x, 30), (x, 170), (0, 0, 0), 2)
    blocks = [
        _ocr_block("项目", 35, 50, 95, 70, 0),
        _ocr_block("年末余额", 155, 50, 225, 70, 1),
        _ocr_block("年初余额", 275, 50, 345, 70, 2),
        _ocr_block("存货", 35, 120, 95, 140, 3),
        _ocr_block("10.00", 165, 120, 215, 140, 4),
        _ocr_block("9.00", 285, 120, 335, 140, 5),
    ]

    tables = reconstruct_scanned_bordered_tables(
        image,
        blocks,
        page_number=1,
        page_width=400,
        page_height=260,
    )

    assert len(tables) == 1
    assert tables[0].raw_content == [
        ["项目", "年末余额", "年初余额"],
        ["存货", "10.00", "9.00"],
    ]


def test_reconstruct_scanned_bordered_table_includes_unruled_left_label_column():
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    image = np.full((260, 400, 3), 255, dtype=np.uint8)
    for y in (30, 100, 170):
        cv2.line(image, (140, y), (380, y), (0, 0, 0), 2)
    for x in (140, 260, 380):
        cv2.line(image, (x, 30), (x, 170), (0, 0, 0), 2)
    blocks = [
        _ocr_block("项目", 80, 50, 130, 70, 0),
        _ocr_block("年末余额", 155, 50, 225, 70, 1),
        _ocr_block("年初余额", 275, 50, 345, 70, 2),
        _ocr_block("存货", 80, 120, 130, 140, 3),
        _ocr_block("10.00", 165, 120, 215, 140, 4),
        _ocr_block("9.00", 285, 120, 335, 140, 5),
    ]

    tables = reconstruct_scanned_bordered_tables(
        image,
        blocks,
        page_number=1,
        page_width=400,
        page_height=260,
    )

    assert len(tables) == 1
    assert tables[0].raw_content == [
        ["项目", "年末余额", "年初余额"],
        ["存货", "10.00", "9.00"],
    ]


def test_reconstruct_scanned_bordered_table_records_merged_cell_span():
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    image = np.full((240, 360, 3), 255, dtype=np.uint8)
    for y in (20, 80, 140, 200):
        cv2.line(image, (20, y), (340, y), (0, 0, 0), 2)
    for x in (20, 180, 340):
        cv2.line(image, (x, 20), (x, 200), (0, 0, 0), 2)
    # Remove the first-row middle divider so the first cell spans two columns.
    cv2.line(image, (180, 23), (180, 77), (255, 255, 255), 7)
    blocks = [
        _ocr_block("merged", 40, 40, 150, 60, 0),
        _ocr_block("r2c1", 40, 100, 100, 120, 1),
        _ocr_block("r2c2", 210, 100, 270, 120, 2),
        _ocr_block("r3c1", 40, 160, 100, 180, 3),
    ]

    tables = reconstruct_scanned_bordered_tables(
        image,
        blocks,
        page_number=1,
        page_width=360,
        page_height=240,
    )

    assert len(tables) == 1
    spans = tables[0].attrs["geometry"]["cell_spans"]
    assert any(span["row"] == 0 and span["col"] == 0 and span["col_span"] == 2 for span in spans)
    result = assemble_parse_result((PageLayout(page_number=1, blocks=tuple(tables)),), {}, "")
    statuses = [cell.geometry_status for row in result.pages[0].tables[0].rows for cell in row.cells]
    assert set(statuses) <= {"exact", "derived"}
    mirror = project_mirror(seal_parse_result(result))
    grid = next(block for block in mirror["blocks"] if block["type"] == "table")["content"]["grid"]
    assert any(cell["row"] == 0 and cell["col"] == 0 and cell["col_span"] == 2 for cell in grid["cells"])


def test_reconstruct_scanned_bordered_table_splits_numeric_tokens_across_row_bands():
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    image = np.full((240, 360, 3), 255, dtype=np.uint8)
    for y in (20, 80, 140, 200):
        cv2.line(image, (20, y), (340, y), (0, 0, 0), 2)
    for x in (20, 180, 340):
        cv2.line(image, (x, 20), (x, 200), (0, 0, 0), 2)
    # The copied scan loses one amount-column divider, but the OCR tokens
    # still occupy distinct row bands.
    cv2.line(image, (183, 140), (337, 140), (255, 255, 255), 7)
    blocks = [
        _ocr_block("项目", 40, 40, 100, 60, 0),
        _ocr_block("金额", 210, 40, 270, 60, 1),
        _ocr_block("存货", 40, 100, 100, 120, 2),
        _ocr_block("10.00", 210, 100, 270, 120, 3),
        _ocr_block("合计", 40, 160, 100, 180, 4),
        _ocr_block("20.00", 210, 160, 270, 180, 5),
    ]

    tables = reconstruct_scanned_bordered_tables(
        image,
        blocks,
        page_number=1,
        page_width=360,
        page_height=240,
    )

    assert tables[0].raw_content == [
        ["项目", "金额"],
        ["存货", "10.00"],
        ["合计", "20.00"],
    ]
    assert tables[0].attrs["geometry"]["merge_diagnostics"]["token_split_vertical_merge_count"] == 1


def test_reconstruct_scanned_bordered_table_splits_label_tokens_with_aligned_amount_rows():
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    image = np.full((240, 360, 3), 255, dtype=np.uint8)
    for y in (20, 80, 140, 200):
        cv2.line(image, (20, y), (340, y), (0, 0, 0), 2)
    for x in (20, 180, 340):
        cv2.line(image, (x, 20), (x, 200), (0, 0, 0), 2)
    # The label-column divider is missing, while the amount column still
    # proves that two physical body rows exist at the same y bands.
    cv2.line(image, (23, 140), (177, 140), (255, 255, 255), 7)
    blocks = [
        _ocr_block("项目", 40, 40, 100, 60, 0),
        _ocr_block("金额", 210, 40, 270, 60, 1),
        _ocr_block("甲公司", 40, 100, 100, 120, 2),
        _ocr_block("10.00", 210, 100, 270, 120, 3),
        _ocr_block("乙公司", 40, 160, 100, 180, 4),
        _ocr_block("20.00", 210, 160, 270, 180, 5),
    ]

    tables = reconstruct_scanned_bordered_tables(
        image,
        blocks,
        page_number=1,
        page_width=360,
        page_height=240,
    )

    assert tables[0].raw_content == [
        ["项目", "金额"],
        ["甲公司", "10.00"],
        ["乙公司", "20.00"],
    ]
    assert tables[0].attrs["geometry"]["merge_diagnostics"]["token_split_vertical_merge_count"] == 1


def test_reconstruct_scanned_bordered_table_splits_subheader_from_first_amount():
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    image = np.full((240, 520, 3), 255, dtype=np.uint8)
    for y in (20, 80, 140, 200):
        cv2.line(image, (20, y), (500, y), (0, 0, 0), 2)
    for x in (20, 180, 340, 500):
        cv2.line(image, (x, 20), (x, 200), (0, 0, 0), 2)
    # Only the first amount-column divider is lost. Its second-level header
    # and first body value must still land in their respective row bands.
    cv2.line(image, (183, 140), (337, 140), (255, 255, 255), 7)
    blocks = [
        _ocr_block("项目", 40, 40, 100, 60, 0),
        _ocr_block("年末余额", 370, 40, 450, 60, 1),
        _ocr_block("账面余额", 210, 100, 290, 120, 2),
        _ocr_block("账面价值", 370, 100, 450, 120, 3),
        _ocr_block("原材料", 40, 160, 100, 180, 4),
        _ocr_block("1,297,676.15", 205, 160, 310, 180, 5),
        _ocr_block("1,297,676.15", 365, 160, 470, 180, 6),
    ]

    tables = reconstruct_scanned_bordered_tables(
        image,
        blocks,
        page_number=1,
        page_width=520,
        page_height=240,
    )

    assert tables[0].raw_content == [
        ["项目", "", "年末余额"],
        ["", "账面余额", "账面价值"],
        ["原材料", "1,297,676.15", "1,297,676.15"],
    ]
    assert tables[0].attrs["geometry"]["merge_diagnostics"]["token_split_vertical_merge_count"] == 1


def test_reconstruct_scanned_bordered_tables_rejects_single_column_notice_frame():
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    image = np.full((300, 400, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (20, 20), (380, 280), (0, 0, 0), 2)
    for y in (90, 160, 230):
        cv2.line(image, (20, y), (380, y), (0, 0, 0), 2)
    blocks = [_ocr_block("notice", 40, 40, 120, 60, 0)]

    assert (
        reconstruct_scanned_bordered_tables(
            image,
            blocks,
            page_number=1,
            page_width=400,
            page_height=300,
        )
        == []
    )


def test_reconstruct_scanned_bordered_table_rejects_l_shaped_merge_component():
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    image = np.full((240, 360, 3), 255, dtype=np.uint8)
    for y in (20, 80, 140, 200):
        cv2.line(image, (20, y), (340, y), (0, 0, 0), 2)
    for x in (20, 180, 340):
        cv2.line(image, (x, 20), (x, 200), (0, 0, 0), 2)
    # Missing top vertical segment joins (0,0)-(0,1); missing left
    # horizontal segment joins (0,0)-(1,0), producing an L component.
    cv2.line(image, (180, 23), (180, 77), (255, 255, 255), 7)
    cv2.line(image, (23, 80), (177, 80), (255, 255, 255), 7)
    blocks = [
        _ocr_block("a", 40, 40, 80, 60, 0),
        _ocr_block("b", 210, 40, 250, 60, 1),
        _ocr_block("c", 40, 100, 80, 120, 2),
        _ocr_block("d", 210, 100, 250, 120, 3),
        _ocr_block("e", 40, 160, 80, 180, 4),
    ]

    tables = reconstruct_scanned_bordered_tables(
        image,
        blocks,
        page_number=1,
        page_width=360,
        page_height=240,
    )

    assert len(tables) == 1
    geometry = tables[0].attrs["geometry"]
    assert geometry["merge_diagnostics"]["rejected_non_rectangular_count"] >= 1
    assert geometry["cell_spans"] == []
