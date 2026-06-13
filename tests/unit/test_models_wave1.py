# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Wave 1 tests: DEC v2.0 normalization, EHL annex, debug artifact."""

from __future__ import annotations

from docmirror.core.debug.artifact import build_debug_artifact
from docmirror.models.entities.domain_result import normalize_domain_result
from docmirror.models.entities.evidence import EvidenceSpan
from docmirror.models.entities.hypothesis import ParseHypothesis
from docmirror.models.entities.parse_result import MirrorAnnex, ParseResult
from docmirror.models.entities.quality_report import ParseQualityReport
from docmirror.models.ehl import attach_quality_report_annex, attach_spans_annex


def _sample_v2_payload() -> dict:
    return {
        "schema_version": "2.0",
        "edition": "community",
        "document": {
            "document_type": "alipay_payment",
            "document_name": "test.pdf",
            "properties": {"region": "CN"},
        },
        "data": {
            "fields": {"account_holder": {"normalized_value": "张三"}},
            "records": [{"amount": "100.00"}],
            "summary": {"total_rows": 1},
        },
        "status": {"success": True, "warnings": ["missing_identity_field:currency"], "errors": []},
        "metadata": {"parser": "docmirror-community"},
    }


class TestEditionV2DecNormalization:
    def test_normalize_edition_v2_table_plugin_output(self):
        dec = normalize_domain_result(_sample_v2_payload())
        assert dec.document_type == "alipay_payment"
        assert dec.entities["account_holder"]["normalized_value"] == "张三"
        assert dec.structured_data["records"] == [{"amount": "100.00"}]
        assert dec.structured_data["summary"]["total_rows"] == 1
        assert dec.properties["region"] == "CN"
        assert any("missing_identity_field" in i for i in dec.quality.issues)

    def test_finalize_extract_accepts_v2(self):
        from docmirror.plugins.runner import _finalize_extract

        pr = ParseResult()
        payload = _sample_v2_payload()
        out = _finalize_extract(pr, payload, edition="community", detected_type="alipay_payment")
        assert out is payload
        assert out["data"]["summary"]["total_rows"] == 1


class TestEhlAnnexWave1:
    def test_attach_spans_annex(self):
        pr = ParseResult()
        spans = [
            EvidenceSpan(id="s1", page=1, kind="rect", source="layout_model"),
            EvidenceSpan(id="s2", page=2, kind="rect", source="ocr"),
        ]
        attach_spans_annex(pr, spans)
        assert pr.annex is not None
        assert pr.annex.evidence_summary is not None
        assert pr.annex.evidence_summary.total_spans == 2
        assert "layout_model" in pr.annex.evidence_summary.by_source

    def test_attach_quality_report_annex(self):
        pr = ParseResult()
        report = ParseQualityReport(document_id="case-1", metrics={"f1": 0.9})
        attach_quality_report_annex(pr, report)
        assert pr.annex.quality_report.document_id == "case-1"

    def test_build_debug_artifact_reads_annex(self):
        pr = ParseResult()
        pr.annex = MirrorAnnex(
            hypotheses=[ParseHypothesis(id="h1", kind="document_type", payload={"category": "x"})],
        )
        artifact = build_debug_artifact(pr)
        assert "hypotheses" in artifact
        assert artifact["hypotheses"][0]["id"] == "h1"
