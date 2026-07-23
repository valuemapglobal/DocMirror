# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for MEP pipeline resolver."""

from __future__ import annotations

from docmirror.configs.middleware.resolver import (
    flatten_profile_middleware_names,
    resolve_pipeline,
)
from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ResultStatus


def _empty_result() -> ParseResult:
    from docmirror.models.entities.parse_result import PageContent

    pr = ParseResult(status=ResultStatus.SUCCESS)
    pr.entities = DocumentEntities()
    pr.pages = [PageContent(page_number=1)]
    return pr


def test_fixed_layout_standard_pipeline():
    names = resolve_pipeline("fixed_layout_rasterizable", "standard")
    for required in [
        "GenericEntityExtractor",
        "GeometricReconstructor",
        "EvidenceEngine",
        "CanonicalDomainEnricher",
        "Validator",
        "LlmDocumentRestorer",
        "HeaderInferrer",
        "HeaderAlignment",
    ]:
        assert required in names
    assert names.index("GeometricReconstructor") < names.index("LlmDocumentRestorer")
    assert names.index("LlmDocumentRestorer") < names.index("HeaderInferrer")
    assert names.index("HeaderInferrer") < names.index("HeaderAlignment")
    assert names.index("HeaderAlignment") < names.index("GenericEntityExtractor")
    assert names.index("GenericEntityExtractor") < names.index("EvidenceEngine")
    assert names.index("EvidenceEngine") < names.index("CanonicalDomainEnricher")
    assert names.index("CanonicalDomainEnricher") < names.index("Validator")
    assert "InstitutionDetector" not in names


def test_fixed_layout_full_includes_tuh():
    names = resolve_pipeline("fixed_layout_rasterizable", "full", _empty_result())
    assert "LanguageDetector" in names
    assert "GeometricReconstructor" in names
    assert "LlmDocumentRestorer" in names
    assert "HeaderInferrer" in names
    assert names.index("LlmDocumentRestorer") < names.index("HeaderInferrer")
    assert "AnomalyDetector" not in names  # disabled unless DOCMIRROR_ENABLE_ANOMALY=1


def test_anomaly_detector_when_env_enabled(monkeypatch):
    monkeypatch.setenv("DOCMIRROR_ENABLE_ANOMALY", "1")
    names = resolve_pipeline("fixed_layout_rasterizable", "full", _empty_result())
    assert "AnomalyDetector" in names


def test_header_inferrer_is_resolved_independent_of_initial_table_count():
    from docmirror.models.entities.parse_result import PageContent, TableBlock

    pr = _empty_result()
    pr.pages[0].tables = [TableBlock(rows=[])]
    names = resolve_pipeline("fixed_layout_rasterizable", "full", pr)
    assert "HeaderInferrer" in names
    assert "HeaderAlignment" in names


def test_container_empty_pipeline():
    assert resolve_pipeline("container", "standard") == []


def test_flatten_v1_list():
    assert flatten_profile_middleware_names(["A", "B"]) == ["A", "B"]


def test_flatten_v2_stages():
    cfg = {
        "stages": {
            "ENRICH": ["GenericEntityExtractor"],
            "VALIDATE": ["Validator"],
            "NORMALIZE": ["LanguageDetector"],
        }
    }
    names = flatten_profile_middleware_names(cfg)
    assert names.index("LanguageDetector") < names.index("GenericEntityExtractor")
    assert names.index("GenericEntityExtractor") < names.index("Validator")
