# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Extractor scene hint must survive keyword_exclude false positives."""

from __future__ import annotations

from docmirror.core.scene.evidence_engine import Evidence, EvidenceEngine
from docmirror.models.entities.parse_result import DocumentEntities, ParseResult


def test_extractor_hint_shields_bank_statement_from_keyword_veto():
    result = ParseResult(
        full_text="贵州银行 银行流水 交易明细",
        entities=DocumentEntities(document_type="unknown"),
    )
    result.entities.domain_specific = {
        "extractor_scene_hint": "bank_statement",
        "extractor_scene_confidence": 0.87,
    }

    engine = EvidenceEngine()
    evidence = [
        Evidence("keyword", "bank_statement", 0.40, 1, "include"),
        Evidence("keyword_exclude", "bank_statement", 100.0, -1, "false veto"),
        Evidence(
            "extractor_scene",
            "bank_statement",
            0.52,
            1,
            "extractor scene_hint=bank_statement conf=0.87",
        ),
    ]
    verdict, confidence, _ = engine._fuse_evidence(
        evidence,
        protected={"bank_statement"},
    )
    assert verdict == "bank_statement"
    assert confidence > 0.3

    classified = engine.process(result)
    assert classified.entities.document_type == "bank_statement"


def test_plugin_document_type_falls_back_to_extractor_hint():
    from docmirror.plugins.runner import _plugin_document_type

    result = ParseResult(
        entities=DocumentEntities(document_type="generic"),
    )
    result.entities.domain_specific = {
        "extractor_scene_hint": "bank_statement",
        "extractor_scene_confidence": 0.87,
    }
    assert _plugin_document_type(result, "generic") == "bank_statement"


def test_filename_evidence_boosts_bank_statement():
    engine = EvidenceEngine()
    result = ParseResult(
        full_text="sample",
        entities=DocumentEntities(document_type="unknown"),
    )
    result.entities.domain_specific = {
        "source_file_name": "ZHAO YA_银行流水_20251104.pdf",
    }
    evidence = engine._filename_evidence(result)
    assert evidence and evidence[0].category == "bank_statement"
    protected = engine._protected_extractor_categories(result)
    assert "bank_statement" in protected
