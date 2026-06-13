import pytest
from docmirror.models.entities.parse_result import ParseResult, DocumentEntities
from docmirror.middlewares.validation.anomaly_detector import AnomalyDetectorMiddleware
import asyncio

def _create_mock_result(credit_accounts: list) -> ParseResult:
    entities = DocumentEntities(domain_specific={"credit_accounts": credit_accounts})
    return ParseResult(
        status="success",
        confidence=1.0,
        pages=[],
        text="",
        errors=[],
        entities=entities
    )

@pytest.mark.asyncio
async def test_anomaly_detector_healthy():
    # Healthy structure
    mock_result = _create_mock_result([
        {"开立日期": "2022.01", "借款金额": "100", "管理机构": "Bank", "账户状态": "正常"},
        {"开立日期": "2023.01", "借款金额": "200", "管理机构": "Bank2", "账户状态": "逾期"}
    ])
    
    middleware = AnomalyDetectorMiddleware()
    result = await middleware.process(mock_result)
    
    assert "REQUIRES_VLM_FALLBACK" not in result.errors
    assert len(middleware.dlq_registry) == 0

@pytest.mark.asyncio
async def test_anomaly_detector_corrupted():
    # 3 accounts: 2 are missing fundamental keys (layout collapsed) -> 66% failure rate
    mock_result = _create_mock_result([
        {"开立日期": "2022.01", "借款金额": "100", "管理机构": "Bank"}, # passing
        {"账户状态": "正常", "余额": "0"}, # failing (missing 开立, 金额, 机构)
        {"账户状态": "结清"} # failing
    ])
    
    middleware = AnomalyDetectorMiddleware()
    result = await middleware.process(mock_result)
    
    assert "REQUIRES_VLM_FALLBACK" in result.errors
    assert len(middleware.dlq_registry) == 1
    assert "Credit extraction collapse" in middleware.dlq_registry[0]["reason"]
