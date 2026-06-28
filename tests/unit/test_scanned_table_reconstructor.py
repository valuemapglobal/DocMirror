from docmirror.input.extraction.scanned_table_reconstructor import reconstruct_scanned_statement_table
from docmirror.models.entities.domain import Block


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
    blocks = [
        _ocr_block("0", 100 + i * 10, 100 + i * 20, 105 + i * 10, 110 + i * 20, i)
        for i in range(12)
    ]

    table = reconstruct_scanned_statement_table(
        blocks,
        page_number=1,
        page_width=595,
        page_height=842,
    )

    assert table is None
