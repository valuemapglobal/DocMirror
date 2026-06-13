# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.

"""Domain plugin schema snapshot tests (Phase 3)."""

from __future__ import annotations

from docmirror.models.entities.domain_result import DomainExtractionResult, normalize_domain_result


def test_bank_statement_schema_snapshot():
    raw = {
        "document_type": "bank_statement",
        "entities": {"交易笔数": 10, "银行名称": "工行"},
        "quality": {
            "confidence": 0.8,
            "trust_score": 0.7,
            "field_coverage": 0.67,
            "validation_passed": True,
            "issues": [],
        },
        "metadata": {"extraction_method": "bank_statement_plugin"},
    }
    result = normalize_domain_result(raw)
    assert isinstance(result, DomainExtractionResult)
    assert result.document_type == "bank_statement"
    assert set(result.model_dump().keys()) == {
        "document_type",
        "properties",
        "entities",
        "structured_data",
        "derived_variables",
        "quality",
        "metadata",
        "evidence_ids",
    }


def test_credit_report_schema_snapshot():
    raw = {
        "document_type": "credit_report",
        "entities": {"姓名": "张三"},
        "quality": {"confidence": 0.7, "trust_score": 0.6, "field_coverage": 0.5, "issues": []},
        "metadata": {"extraction_mode": "fast"},
    }
    result = normalize_domain_result(raw)
    dumped = result.model_dump()
    assert dumped["document_type"] == "credit_report"
    assert dumped["entities"]["姓名"] == "张三"
    assert dumped["quality"]["confidence"] == 0.7
