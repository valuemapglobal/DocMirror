# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from docmirror.configs.runtime.performance import DocumentWorkloadSignals, resolve_semantic_worker_budget
from docmirror.models.mirror.semantic_contract import partition_domain_specific, validate_domain_specific_keys
from docmirror.models.schemas.registry import (
    get_projection_schema,
    load_projection_registry,
    validate_projection_payload,
)


def test_mirror_quality_metric_layering():
    from docmirror.models.entities.parse_result import ParseResult, ResultStatus, TrustResult

    pr = ParseResult(status=ResultStatus.SUCCESS, confidence=0.82)
    pr.trust = TrustResult(trust_score=0.91, validation_passed=True, forgery_reasons=[])
    api = pr.to_api_dict()
    quality = api["data"]["quality"]
    assert quality["classification"]["confidence"] == 0.82
    assert quality["mirror_fidelity"]["score"] == 0.91
    assert quality["trust_score"] == 0.91


def test_semantic_worker_budget_boosts_heavy_documents():
    light = resolve_semantic_worker_budget(4, signals=DocumentWorkloadSignals(page_count=2))
    heavy = resolve_semantic_worker_budget(
        4,
        signals=DocumentWorkloadSignals(
            page_count=40,
            image_page_ratio=0.9,
            table_page_ratio=0.8,
            ocr_probability=0.9,
        ),
    )
    assert heavy.total >= light.total


def test_domain_specific_partition():
    ds = {
        "plugin_document_type": "bank_statement",
        "entity_merge_hints": [{"id": "a"}],
        "custom_field": "x",
    }
    mirror, semantic = partition_domain_specific(ds)
    assert mirror["plugin_document_type"] == "bank_statement"
    assert mirror["custom_field"] == "x"
    assert "entity_merge_hints" in semantic


def test_projection_schema_registry():
    registry = load_projection_registry()
    assert "mirror" in registry
    assert "community" in registry
    assert get_projection_schema("mirror").version == "1.1"


def test_projection_schema_runtime_validation():
    valid = validate_projection_payload(
        "community",
        {
            "schema_version": "2.0",
            "edition": "community",
            "document": {},
            "data": {},
        },
    )
    invalid = validate_projection_payload("community", {"edition": "community"})

    assert valid.valid is True
    assert invalid.valid is False


def test_reasoning_layer_noop_report_is_read_only():
    from docmirror.core.reasoning import NoOpReasoner
    from docmirror.models.entities.parse_result import ParseResult, ResultStatus

    mirror = ParseResult(status=ResultStatus.SUCCESS)
    before = mirror.model_dump_json()

    report = NoOpReasoner().explain(mirror, {"community": {"edition": "community"}})

    assert report.to_dict()["summary"] == ""
    assert mirror.model_dump_json() == before
