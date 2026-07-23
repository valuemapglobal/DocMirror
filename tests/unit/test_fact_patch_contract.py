# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest
from pydantic import ValidationError

from docmirror.input.canonical.fact_patch import CanonicalPatch, apply_canonical_patch, validate_canonical_patch
from docmirror.models.entities.parse_result import CanonicalEvidencePlane, DocumentEntities, ParseResult
from docmirror.models.mirror.vnext import EvidenceAtom, EvidenceStore


def test_fact_patch_applies_facts_with_field_level_mutation_audit():
    result = ParseResult(entities=DocumentEntities(document_type="unknown"))
    patch = CanonicalPatch(
        capability_id="bank_statement",
        document_type="bank_statement",
        entity_fields={"subject_name": "Alice"},
        domain_facts={"currency": "CNY"},
        datasets={"transactions": [{"record_id": "tx:r000001", "amount": "1.00"}]},
        confidence=0.9,
    )

    result = apply_canonical_patch(result, patch)

    assert result.entities.document_type == "bank_statement"
    assert result.entities.subject_name == "Alice"
    assert result.entities.domain_specific["currency"] == "CNY"
    assert result.entities.domain_specific["transactions"][0]["record_id"] == "tx:r000001"
    changed = {mutation.field_changed for mutation in result.mutations}
    assert "entities.document_type" in changed
    assert "entities.subject_name" in changed
    assert "entities.domain_specific.currency" in changed
    assert "entities.domain_specific.transactions" in changed
    assert all(mutation.middleware_name == "canonical:bank_statement" for mutation in result.mutations)


def test_fact_patch_existing_fact_wins_without_explicit_replace():
    result = ParseResult(entities=DocumentEntities(subject_name="Canonical"))
    result = apply_canonical_patch(
        result,
        CanonicalPatch(capability_id="test", entity_fields={"subject_name": "Plugin"}),
    )
    assert result.entities.subject_name == "Canonical"
    assert result.mutations == []


def test_fact_patch_explicit_replace_is_audited():
    result = ParseResult(
        entities=DocumentEntities(subject_name="Old"),
        evidence_plane=CanonicalEvidencePlane(
            evidence=EvidenceStore(text_atoms=[EvidenceAtom(id="ev:replacement", text="New")])
        ),
    )
    result = apply_canonical_patch(
        result,
        CanonicalPatch(
            capability_id="test",
            entity_fields={"subject_name": "New"},
            evidence_ids=("ev:replacement",),
            replace_paths=frozenset({"entities.subject_name"}),
            reason="higher-confidence evidence",
        ),
    )
    assert result.entities.subject_name == "New"
    assert result.mutations[0].old_value == "Old"
    assert result.mutations[0].new_value == "New"
    assert result.mutations[0].reason == "higher-confidence evidence"


def test_fact_patch_replacement_requires_traceable_evidence():
    result = ParseResult(entities=DocumentEntities(subject_name="Old"))

    with pytest.raises(ValueError, match="requires evidence_ids"):
        apply_canonical_patch(
            result,
            CanonicalPatch(
                capability_id="test",
                entity_fields={"subject_name": "New"},
                replace_paths=frozenset({"entities.subject_name"}),
                reason="higher-confidence evidence",
            ),
        )

    with pytest.raises(ValueError, match="unknown evidence_ids"):
        apply_canonical_patch(
            result,
            CanonicalPatch(
                capability_id="test",
                entity_fields={"subject_name": "New"},
                evidence_ids=("ev:missing",),
                replace_paths=frozenset({"entities.subject_name"}),
                reason="higher-confidence evidence",
            ),
        )


def test_fact_patch_rejects_duplicate_dataset_record_ids():
    with pytest.raises(ValidationError, match="duplicate record_id"):
        CanonicalPatch(
            capability_id="test",
            datasets={
                "rows": [
                    {"record_id": "same"},
                    {"record_id": "same"},
                ]
            },
        )


@pytest.mark.parametrize("key", ["edition", "schema_version", "artifact", "license", "markdown"])
def test_fact_patch_rejects_delivery_concerns_at_canonical_boundary(key: str):
    patch = CanonicalPatch(capability_id="test", domain_facts={key: "not-a-fact"})
    with pytest.raises(ValueError, match="delivery-only"):
        validate_canonical_patch(patch)


def test_native_recognizer_runs_against_copy_not_canonical_result(monkeypatch):
    from docmirror.framework.middlewares.extraction import community_fact_recognizer as enrichment

    result = ParseResult(entities=DocumentEntities(document_type="business_license"))

    class _Recognizer:
        capability_id = "copy-test"

        @staticmethod
        def recognize_facts(read_view, _full_text):
            read_view.entities.subject_name = "mutated copy"
            return CanonicalPatch(capability_id="copy-test", entity_fields={"organization": "Acme"})

    monkeypatch.setattr(enrichment, "_load_canonical_capability", lambda _domain: _Recognizer())

    patch = enrichment.run_canonical_enrichment(result)

    assert result.entities.subject_name is None
    assert patch.entity_fields["organization"] == "Acme"


def test_fact_patch_is_transactional_when_late_section_validation_fails():
    result = ParseResult(entities=DocumentEntities(document_type="unknown"))
    before = result.model_dump(mode="json")
    patch = CanonicalPatch(
        capability_id="test",
        document_type="business_license",
        domain_facts={"company_name": "Acme"},
        sections=({"page_start": "not-an-integer"},),
    )

    with pytest.raises((TypeError, ValueError)):
        apply_canonical_patch(result, patch)

    assert result.model_dump(mode="json") == before


def test_recognizer_exception_returns_zero_change_patch_and_preserves_core(monkeypatch):
    from docmirror.framework.middlewares.extraction import community_fact_recognizer as enrichment

    result = ParseResult(entities=DocumentEntities(document_type="business_license"))
    before = result.fact_fingerprint()

    class _BrokenRecognizer:
        capability_id = "broken"

        @staticmethod
        def recognize_facts(read_view, _text):
            read_view.entities.subject_name = "must not escape"
            raise RuntimeError("boom")

    monkeypatch.setattr(enrichment, "_load_canonical_capability", lambda _domain: _BrokenRecognizer())
    patch = enrichment.run_canonical_enrichment(result)
    candidate = apply_canonical_patch(result, patch)

    assert patch.capability_id == "business_license"
    assert not patch.entity_fields and not patch.domain_facts and not patch.datasets
    assert result.fact_fingerprint() == before
    assert candidate.fact_fingerprint() == before


def test_recognizer_timeout_returns_zero_change_patch(monkeypatch):
    import time

    from docmirror.framework.middlewares.extraction import community_fact_recognizer as enrichment

    result = ParseResult(entities=DocumentEntities(document_type="business_license"))
    before = result.fact_fingerprint()

    class _SlowRecognizer:
        capability_id = "slow"

        @staticmethod
        def recognize_facts(read_view, _text):
            time.sleep(0.2)
            read_view.entities.subject_name = "late mutation"
            return CanonicalPatch(capability_id="slow", entity_fields={"subject_name": "late"})

    monkeypatch.setattr(enrichment, "_load_canonical_capability", lambda _domain: _SlowRecognizer())
    monkeypatch.setattr(enrichment, "CANONICAL_ENRICH_TIMEOUT_SECONDS", 0.01)
    started = time.perf_counter()
    patch = enrichment.run_canonical_enrichment(result)

    assert time.perf_counter() - started < 0.1
    assert not patch.entity_fields
    assert result.fact_fingerprint() == before
