import pytest

from docmirror.framework.middlewares.validation.anomaly_detector import AnomalyDetectorMiddleware
from docmirror.models.entities.parse_result import (
    CellValue,
    DocumentEntities,
    PageContent,
    ParseResult,
    RowType,
    TableBlock,
    TableRow,
)


def _create_mock_result(credit_accounts: list) -> ParseResult:
    entities = DocumentEntities(domain_specific={"credit_accounts": credit_accounts})
    return ParseResult(
        status="success",
        confidence=1.0,
        pages=[],
        text="",
        errors=[],
        entities=entities,
    )


def _table_result(rows: list[TableRow], headers: list[str]) -> ParseResult:
    table = TableBlock(table_id="t0", headers=headers, rows=rows, page=1)
    page = PageContent(page_number=1, tables=[table])
    return ParseResult(
        status="success",
        confidence=1.0,
        pages=[page],
        text="",
        errors=[],
        entities=DocumentEntities(),
    )


def test_anomaly_detector_healthy():
    mock_result = _create_mock_result([
        {"开立日期": "2022.01", "借款金额": "100", "管理机构": "Bank", "账户状态": "正常"},
        {"开立日期": "2023.01", "借款金额": "200", "管理机构": "Bank2", "账户状态": "逾期"},
    ])

    middleware = AnomalyDetectorMiddleware()
    result = middleware.process(mock_result)

    assert "REQUIRES_VLM_FALLBACK" not in result.errors
    assert len(middleware.dlq_registry) == 0


def test_anomaly_detector_corrupted():
    mock_result = _create_mock_result([
        {"开立日期": "2022.01", "借款金额": "100", "管理机构": "Bank"},
        {"账户状态": "正常", "余额": "0"},
        {"账户状态": "结清"},
    ])

    middleware = AnomalyDetectorMiddleware()
    result = middleware.process(mock_result)

    assert "REQUIRES_VLM_FALLBACK" in result.errors
    assert len(middleware.dlq_registry) == 1
    assert "Credit extraction collapse" in middleware.dlq_registry[0]["reason"]


def test_anomaly_detector_table_collapse():
    headers = ["交易日期", "摘要", "金额", "余额"]
    sparse_rows = [
        TableRow(
            cells=[CellValue(text=""), CellValue(text=""), CellValue(text=""), CellValue(text="")],
            row_type=RowType.DATA,
        )
        for _ in range(4)
    ]
    mock_result = _table_result(sparse_rows, headers)

    middleware = AnomalyDetectorMiddleware()
    result = middleware.process(mock_result)

    assert "REQUIRES_VLM_FALLBACK" in result.errors
    report = result.entities.domain_specific["structural_anomaly_report"]
    assert report["type"] == "table_structure_collapse"
    assert len(middleware.dlq_registry) == 1
