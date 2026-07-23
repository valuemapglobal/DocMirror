# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from docmirror.configs.runtime.performance import DocumentWorkloadSignals, resolve_semantic_worker_budget
from docmirror.models.mirror.semantic_contract import partition_domain_specific, validate_domain_specific_keys
from docmirror.models.schemas.registry import (
    get_projection_schema,
    load_projection_registry,
    validate_projection_payload,
)
from docmirror.models.sealed import seal_parse_result
from docmirror.output.mirror_projector import project_mirror


def test_mirror_quality_metric_layering():
    from docmirror.models.entities.parse_result import ParseResult, ResultStatus, TrustResult

    pr = ParseResult(status=ResultStatus.SUCCESS, confidence=0.82)
    pr.trust = TrustResult(trust_score=0.91, validation_passed=True, forgery_reasons=[])
    api = project_mirror(seal_parse_result(pr))
    quality = api["quality"]
    assert quality["overall"]["score"] == 1.0
    assert quality["overall"]["status"] == "pass"
    assert "data" not in api


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
        "canonical_document_type": "bank_statement",
        "entity_merge_hints": [{"id": "a"}],
        "custom_field": "x",
    }
    mirror, semantic = partition_domain_specific(ds)
    assert mirror["canonical_document_type"] == "bank_statement"
    assert mirror["custom_field"] == "x"
    assert "entity_merge_hints" in semantic


def test_projection_schema_registry():
    registry = load_projection_registry()
    assert "mirror" in registry
    assert "community" in registry
    assert get_projection_schema("mirror").version == "1.1"
    assert get_projection_schema("community").version == "3.0.0"
    assert get_projection_schema("community").compatibility == "current-major; explicit-v2-exporter-required"
    assert get_projection_schema("community_v2").version == "2.2"


def test_projection_schema_runtime_validation():
    valid = validate_projection_payload(
        "community",
        {
            "schema": {
                "name": "docmirror.community",
                "version": "3.0.0",
                "edition": "community",
                "domain": "generic",
                "support_level": "generic",
            },
            "document": {
                "id": "doc_test",
                "type": "generic",
                "title": "Test",
                "page_count": 0,
                "language": ["en"],
                "source_file": {"name": "", "mime_type": "application/octet-stream", "sha256": ""},
                "units": {},
            },
            "sections": [],
            "datasets": [],
            "files": {
                "content_md": "001_content.md",
                "datasets_dir": "001_datasets",
                "dataset_audit_csv": "001_datasets/_audit_cells.csv",
            },
            "warnings": [],
        },
    )
    invalid = validate_projection_payload("community", {"edition": "community"})

    assert valid.valid is True
    assert invalid.valid is False


def test_community_22_schema_requires_consumer_contract_blocks():
    invalid = validate_projection_payload(
        "community_v2",
        {
            "$schema": "https://valuemapglobal.github.io/DocMirror/schemas/edition_community.schema.json",
            "schema_version": "2.2",
            "edition": "community",
            "document": {},
            "data": {},
        },
    )

    assert invalid.valid is False
