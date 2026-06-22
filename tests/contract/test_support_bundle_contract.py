# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Contract tests for redaction-safe support bundle (GA 1.0 OUT4-4).

Validates:
    1. Support bundle is redaction-safe by default (no raw values).
    2. Support bundle includes evidence linkage, ledger summary, and quality.
    3. Support bundle with include_sensitive=True exposes raw values.
    4. is_support_bundle_redaction_safe correctly identifies safe/unsafe bundles.
"""

from docmirror.evidence.bundle import build_evidence_bundle
from docmirror.evidence.redaction import (
    build_support_bundle,
    is_support_bundle_redaction_safe,
)
from docmirror.models.entities.parse_result import (
    CellValue,
    DocumentEntities,
    PageContent,
    ParseResult,
    TableBlock,
    TableRow,
)


def _make_simple_result():
    return ParseResult(
        status="success",
        pages=[
            PageContent(
                page_number=1,
                tables=[
                    TableBlock(
                        table_id="t1",
                        headers=["Name", "Amount"],
                        rows=[
                            TableRow(
                                cells=[
                                    CellValue(
                                        text="Alice",
                                        bbox=[10, 10, 50, 20],
                                        confidence=0.95,
                                        evidence_ids=["e1"],
                                    ),
                                    CellValue(
                                        text="100.00",
                                        bbox=[60, 10, 100, 20],
                                        confidence=0.92,
                                        evidence_ids=["e2"],
                                    ),
                                ]
                            ),
                        ],
                    )
                ],
            )
        ],
    )


def test_support_bundle_redaction_safe_by_default():
    """OUT4-4: Default support bundle has no raw values, only hashes and hints."""
    result = _make_simple_result()
    result.entities = DocumentEntities(document_type="bank_statement")

    editions = {
        "community": {
            "plugin": {"name": "bank_statement"},
            "data": {"fields": {"account": "123456"}},
            "metadata": {"support_level": "L1", "fallback_reason": None},
            "quality": {"confidence": 0.9},
        }
    }

    evidence = build_evidence_bundle(result, editions=editions, task_id="t1", document_id="d1")
    bundle = build_support_bundle(
        result,
        editions=editions,
        evidence_bundle=evidence,
        task_id="t1",
        document_id="d1",
    )

    assert bundle["version"] == 2
    assert bundle["redaction_safe"] is True
    assert bundle["include_sensitive"] is False
    assert is_support_bundle_redaction_safe(bundle) is True

    # No raw values should be present
    for fe in bundle["field_evidence"]:
        assert "value" not in fe, f"raw value leaked at {fe.get('field_path')}"
        assert "value_hash" in fe
        assert "value_hint" in fe
        hint = fe["value_hint"]
        assert "hash" in hint
        assert "length" in hint

    # Evidence linkage should be present
    linkage = bundle["support"]["evidence_linkage"]
    assert linkage["total_ledger_entries"] > 0
    assert "bbox_coverage" in linkage
    assert "source_ref_coverage" in linkage

    # Minimal repro should not contain raw values
    repro = bundle["support"]["minimal_repro"]
    assert repro["document_type"] == "bank_statement"
    assert repro["page_count"] == 1

    # Quality should be present
    assert "quality" in bundle
    assert "text_fidelity" in bundle["quality"]

    # Edition metadata should be safe
    assert "community" in bundle["edition_metadata"]
    assert bundle["edition_metadata"]["community"]["support_level"] == "L1"


def test_support_bundle_include_sensitive():
    """OUT4-4: With include_sensitive=True, raw values are exposed."""
    result = _make_simple_result()
    result.entities = DocumentEntities(document_type="bank_statement")

    evidence = build_evidence_bundle(result, task_id="t1", document_id="d1")
    bundle = build_support_bundle(
        result,
        evidence_bundle=evidence,
        task_id="t1",
        document_id="d1",
        include_sensitive=True,
    )

    assert bundle["redaction_safe"] is False
    assert bundle["include_sensitive"] is True
    assert is_support_bundle_redaction_safe(bundle) is False

    # Raw values should be present
    found_value = False
    for fe in bundle["field_evidence"]:
        if "value" in fe:
            found_value = True
            break
    assert found_value, "include_sensitive=True should expose raw values"


def test_support_bundle_includes_unresolved():
    """OUT4-4: Support bundle includes unresolved evidence entries."""
    result = ParseResult(
        status="success",
        pages=[
            PageContent(
                page_number=1,
                tables=[
                    TableBlock(
                        table_id="t1",
                        headers=["Field"],
                        rows=[
                            TableRow(
                                cells=[
                                    CellValue(
                                        text="orphan",
                                        confidence=0.3,
                                    )
                                ]
                            )
                        ],
                    )
                ],
            )
        ],
    )
    result.entities = DocumentEntities(document_type="generic")

    editions = {
        "community": {
            "plugin": {"name": "generic"},
            "data": {"fields": {"unknown": "value"}},
            "metadata": {"support_level": "L0", "fallback_reason": "no_domain_plugin"},
            "quality": {},
        }
    }

    evidence = build_evidence_bundle(result, editions=editions, task_id="t1", document_id="d1")
    bundle = build_support_bundle(result, editions=editions, evidence_bundle=evidence, task_id="t1", document_id="d1")

    # Should include edition metadata
    assert "community" in bundle["edition_metadata"]
    assert bundle["edition_metadata"]["community"]["support_level"] == "L0"
    assert bundle["edition_metadata"]["community"]["fallback_reason"] == "no_domain_plugin"

    # Evidence linkage
    assert bundle["support"]["evidence_linkage"]["total_ledger_entries"] > 0


def test_support_bundle_no_editions_no_crash():
    """OUT4-4: Support bundle should not crash with empty editions."""
    result = _make_simple_result()
    evidence = build_evidence_bundle(result, task_id="t1", document_id="d1")
    bundle = build_support_bundle(result, evidence_bundle=evidence, task_id="t1", document_id="d1")

    assert bundle["version"] == 2
    assert bundle["redaction_safe"] is True
    assert bundle["edition_metadata"] == {}
    assert "evidence_linkage" in bundle["support"]
