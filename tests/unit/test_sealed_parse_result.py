# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from docmirror.models.entities.parse_result import CanonicalEvidencePlane, DocumentEntities, ParseResult
from docmirror.models.mirror.vnext import SourceInfo
from docmirror.models.sealed import SealedParseResult, seal_parse_result


def test_seal_is_idempotent_and_drops_mutable_source_reference():
    source = ParseResult(entities=DocumentEntities(document_type="bank_statement"))
    sealed = seal_parse_result(source)
    assert seal_parse_result(sealed) is sealed

    source.entities.document_type = "mutated_after_seal"
    assert sealed.entities.document_type == "bank_statement"
    assert sealed.verify_integrity()


def test_each_projector_read_view_is_isolated():
    sealed = seal_parse_result(
        ParseResult(
            entities=DocumentEntities(
                document_type="bank_statement",
                domain_specific={"currency": "CNY", "rows": [{"record_id": "r1"}]},
            )
        )
    )
    first = sealed.to_read_view()
    second = sealed.to_read_view()

    first.entities.document_type = "evil"
    first.entities.domain_specific["rows"][0]["record_id"] = "evil"

    assert second.entities.document_type == "bank_statement"
    assert second.entities.domain_specific["rows"][0]["record_id"] == "r1"
    assert sealed.to_read_view().entities.document_type == "bank_statement"
    assert sealed.verify_integrity()


def test_sealed_envelope_cannot_be_reassigned():
    sealed = seal_parse_result(ParseResult())
    with pytest.raises(FrozenInstanceError):
        sealed.fingerprint = "changed"  # type: ignore[misc]


def test_sealed_constructor_rejects_tampered_bytes():
    sealed = seal_parse_result(ParseResult())
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        SealedParseResult(_canonical_json=sealed._canonical_json + b" ", fingerprint=sealed.fingerprint)


def test_fact_fingerprint_excludes_runtime_metadata_but_integrity_does_not():
    first = ParseResult(entities=DocumentEntities(document_type="bank_statement"))
    second = first.model_copy(deep=True)
    first.parser_info.elapsed_ms = 10
    second.parser_info.elapsed_ms = 999

    sealed_first = seal_parse_result(first)
    sealed_second = seal_parse_result(second)

    assert sealed_first.fact_fingerprint() == sealed_second.fact_fingerprint()
    assert sealed_first.integrity_fingerprint != sealed_second.integrity_fingerprint


def test_fact_fingerprint_excludes_staging_path_and_legacy_step_timings():
    first = ParseResult(
        entities=DocumentEntities(domain_specific={"step_timings": {"EvidenceEngine": 1.0}}),
        evidence_plane=CanonicalEvidencePlane(source=SourceInfo(provenance={"path": "/tmp/accepted-a/source.pdf"})),
    )
    second = first.model_copy(deep=True)
    second.entities.domain_specific["step_timings"] = {"EvidenceEngine": 999.0}
    second.evidence_plane.source.provenance["path"] = "/tmp/accepted-b/source.pdf"

    assert first.fact_fingerprint() == second.fact_fingerprint()
    assert seal_parse_result(first).integrity_fingerprint != seal_parse_result(second).integrity_fingerprint
