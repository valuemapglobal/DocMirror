# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""DEC validation tests (design 09 Phase 3)."""

from __future__ import annotations

from docmirror.models.entities.domain_result import DomainExtractionResult, normalize_domain_result
from docmirror.models.schemas.loader import load_schema_registry, validate_dec


class TestDecValidation:
    def test_normalize_wrapper_dict(self):
        raw = {
            "document_type": "credit_report",
            "entities": {"name": "张三"},
            "quality": {"confidence": 0.9},
        }
        dec = normalize_domain_result(raw)
        assert dec.document_type == "credit_report"
        assert dec.entities["name"] == "张三"
        assert dec.quality.confidence == 0.9

    def test_registry_loads(self):
        reg = load_schema_registry()
        assert "bank_statement" in reg
        assert "wechat_payment" in reg
        assert "credit_report" not in reg

    def test_validate_dec_unregistered_type_no_issues(self):
        dec = DomainExtractionResult(document_type="passport")
        assert validate_dec(dec) == []

    def test_validate_dec_bank_statement_empty_issues(self):
        dec = DomainExtractionResult(document_type="bank_statement", structured_data=[])
        issues = validate_dec(dec)
        assert any("bank_statement" in i for i in issues)
