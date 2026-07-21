from docmirror.framework.middlewares.extraction.header_inferrer import HeaderInferrerMiddleware
from docmirror.models.entities.parse_result import CellValue, PageContent, ParseResult, TableBlock, TableRow


def test_header_inferrer_preserves_scanned_statement_grid_headers():
    table = TableBlock(
        table_id="pt_1_0",
        headers=["项目", "附注", "年末余额", "年初余额"],
        rows=[
            TableRow(
                cells=[
                    CellValue(text="货币资金"),
                    CellValue(text="六、1"),
                    CellValue(text="144.00"),
                    CellValue(text="116.00"),
                ]
            ),
            TableRow(
                cells=[
                    CellValue(text="应收账款"),
                    CellValue(text="六、2"),
                    CellValue(text="474.00"),
                    CellValue(text="415.00"),
                ]
            ),
            TableRow(
                cells=[
                    CellValue(text="资产总计"),
                    CellValue(text=""),
                    CellValue(text="1741.00"),
                    CellValue(text="1634.00"),
                ]
            ),
        ],
        extraction_layer="scanned_ocr_statement_grid",
        metadata={"preserve_headers": True},
    )
    result = ParseResult(pages=[PageContent(page_number=1, tables=[table])])

    out = HeaderInferrerMiddleware().process(result)

    assert out.pages[0].tables[0].headers == ["项目", "附注", "年末余额", "年初余额"]
    assert len(out.mutations) == 0


def test_header_inferrer_marks_promoted_transaction_header_as_data() -> None:
    table = TableBlock(
        table_id="pt_2_0",
        headers=["支出", "商户", "47.40", "2023-06-11 23:08:45"],
        rows=[
            TableRow(
                cells=[
                    CellValue(text="收入"),
                    CellValue(text="商户A"),
                    CellValue(text="0.10"),
                    CellValue(text="2023-06-11 14:43:14"),
                ]
            ),
            TableRow(
                cells=[
                    CellValue(text="支出"),
                    CellValue(text="商户B"),
                    CellValue(text="8.00"),
                    CellValue(text="2023-06-10 10:00:00"),
                ]
            ),
            TableRow(
                cells=[
                    CellValue(text="收入"),
                    CellValue(text="商户C"),
                    CellValue(text="1.00"),
                    CellValue(text="2023-06-09 10:00:00"),
                ]
            ),
        ],
        metadata={"preserve_headers": True},
    )
    result = ParseResult(pages=[PageContent(page_number=2, tables=[table])])

    HeaderInferrerMiddleware().process(result)

    assert table.metadata["preserve_headers"] is False
    assert table.metadata["header_source"] == "data_row"
