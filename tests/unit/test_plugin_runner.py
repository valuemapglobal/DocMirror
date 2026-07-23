# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for fixed Core canonical enrichment selection."""

from __future__ import annotations

from docmirror.framework.middlewares.extraction import community_fact_recognizer as enrichment
from docmirror.input.canonical.fact_patch import CanonicalPatch
from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ResultStatus


def _result(document_type: str = "unknown") -> ParseResult:
    return ParseResult(
        status=ResultStatus.SUCCESS,
        entities=DocumentEntities(document_type=document_type),
    )


class _Capability:
    capability_id = "test-capability"

    def recognize_facts(self, result: ParseResult, text: str) -> CanonicalPatch:
        return CanonicalPatch(
            capability_id=self.capability_id,
            document_type=result.entities.document_type,
            domain_facts={"observed_text": text},
        )


def test_enrichment_selects_fixed_capability(monkeypatch) -> None:
    selected: list[str] = []

    def _load(domain: str):
        selected.append(domain)
        return _Capability()

    monkeypatch.setattr(enrichment, "_load_canonical_capability", _load)
    patch = enrichment.run_canonical_enrichment(_result("bank_statement"), full_text="ledger")

    assert selected == ["bank_statement"]
    assert patch.capability_id == "test-capability"
    assert patch.domain_facts == {"observed_text": "ledger"}


def test_enrichment_uses_forced_document_type_hint(monkeypatch) -> None:
    result = _result("unknown")
    result.entities.domain_specific = {
        "user_doc_type_hint": "vat_invoice",
        "user_doc_type_hint_strength": "force",
    }
    selected: list[str] = []

    monkeypatch.setattr(
        enrichment,
        "_load_canonical_capability",
        lambda domain: selected.append(domain) or _Capability(),
    )
    enrichment.run_canonical_enrichment(result)

    assert selected == ["vat_invoice"]


def test_unknown_document_uses_fixed_generic_capability(monkeypatch) -> None:
    selected: list[str] = []
    monkeypatch.setattr(
        enrichment,
        "_load_canonical_capability",
        lambda domain: selected.append(domain) or _Capability(),
    )

    enrichment.run_canonical_enrichment(_result("unregistered_document"))

    assert selected == ["generic"]


def test_enrichment_does_not_import_plugin_runtime() -> None:
    source = enrichment.__file__
    assert source is not None
    text = open(source, encoding="utf-8").read()
    assert "docmirror.plugins._runtime" not in text
    assert "PluginRegistry" not in text
