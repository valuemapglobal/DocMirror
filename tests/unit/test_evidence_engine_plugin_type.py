# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""M9: EvidenceEngine plugin_document_type hint for PEC routing."""

from __future__ import annotations

from unittest.mock import patch

from docmirror.layout.scene.evidence_engine import EvidenceEngine
from docmirror.layout.scene.evidence_types import Evidence
from docmirror.models.entities.parse_result import DocumentEntities, PageContent, ParseResult, TextBlock


def test_evidence_engine_sets_plugin_document_type_alias():
    result = ParseResult(
        full_text="银行对账单 sample",
        entities=DocumentEntities(document_type="unknown"),
    )
    with patch.object(
        EvidenceEngine,
        "_fuse_evidence",
        return_value=("bank_reconciliation", 0.95, []),
    ):
        out = EvidenceEngine().process(result)
    ds = out.entities.domain_specific or {}
    assert out.entities.document_type == "bank_reconciliation"
    assert ds.get("plugin_document_type") == "bank_statement"


def test_evidence_engine_maps_enterprise_credit_to_community_credit_plugin():
    assert EvidenceEngine._edition_document_type("credit_report_enterprise") == "credit_report"


def test_enterprise_credit_cover_beats_long_appendix_keyword_conflict():
    result = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                texts=[TextBlock(content="企业信用报告 报告编号 NO.1 中征码 123 报告时间 2026-01-01")],
            )
        ],
        entities=DocumentEntities(document_type="unknown"),
    )
    competing = [
        Evidence(source="keyword", category="bill_of_exchange", weight=0.50, direction=1, detail="competing"),
        Evidence(source="keyword", category="credit_report", weight=0.45, direction=1, detail="baseline"),
    ]
    with (
        patch.object(EvidenceEngine, "_keyword_evidence", return_value=competing),
        patch.object(EvidenceEngine, "_header_evidence", return_value=[]),
        patch.object(EvidenceEngine, "_entity_evidence", return_value=[]),
        patch.object(EvidenceEngine, "_visual_evidence", return_value=[]),
    ):
        out = EvidenceEngine().process(result)

    assert out.entities.document_type == "credit_report"
