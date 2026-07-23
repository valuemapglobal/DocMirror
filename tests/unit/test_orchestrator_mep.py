# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Orchestrator MEP pipeline resolution smoke tests."""

from __future__ import annotations

from docmirror.framework.orchestrator import Orchestrator
from docmirror.models.entities.parse_result import DocumentEntities, PageContent, ParseResult, ResultStatus


def _minimal_result(*, tables: bool = False) -> ParseResult:
    page = PageContent(page_number=1)
    if tables:
        from docmirror.models.entities.parse_result import TableBlock

        page.tables = [TableBlock(rows=[])]
    pr = ParseResult(status=ResultStatus.SUCCESS, pages=[page])
    pr.entities = DocumentEntities()
    return pr


def test_orchestrator_standard_fixed_layout_chain():
    orch = Orchestrator()
    mws = orch._build_middlewares("standard", "pdf", "fixed_layout_rasterizable", _minimal_result())
    names = [type(m).__name__ for m in mws]
    for required in [
        "GenericEntityExtractor",
        "GeometricReconstructor",
        "EvidenceEngine",
        "CommunityFactRecognizer",
        "Validator",
        "LlmDocumentRestorer",
        "HeaderInferrerMiddleware",
        "HeaderAlignmentMiddleware",
    ]:
        assert required in names
    assert names.index("GeometricReconstructor") < names.index("LlmDocumentRestorer")
    assert names.index("LlmDocumentRestorer") < names.index("HeaderInferrerMiddleware")
    assert names.index("HeaderInferrerMiddleware") < names.index("HeaderAlignmentMiddleware")
    assert names.index("HeaderAlignmentMiddleware") < names.index("GenericEntityExtractor")
    assert names.index("GenericEntityExtractor") < names.index("EvidenceEngine")
    assert names.index("EvidenceEngine") < names.index("CommunityFactRecognizer")
    assert names.index("CommunityFactRecognizer") < names.index("Validator")
    assert "InstitutionDetector" not in names


def test_orchestrator_full_keeps_causal_structure_chain(monkeypatch):
    monkeypatch.setenv("DOCMIRROR_ENABLE_ANOMALY", "1")
    orch = Orchestrator()
    mws = orch._build_middlewares("full", "pdf", "fixed_layout_rasterizable", _minimal_result())
    class_names = {type(m).__name__ for m in mws}
    assert "LanguageDetector" in class_names
    assert "GeometricReconstructor" in class_names
    assert "LlmDocumentRestorer" in class_names
    assert "HeaderInferrerMiddleware" in class_names
    assert "AnomalyDetectorMiddleware" in class_names


def test_orchestrator_raw_mode_skips_build():
    orch = Orchestrator()
    import asyncio

    result = _minimal_result()
    out = asyncio.run(orch.enhance(result, enhance_mode="raw", file_type="pdf"))
    assert out.entities.domain_specific.get("step_timings") is None
