# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""P1 plugin absence, failure, and timeout cannot alter canonical facts."""

from __future__ import annotations

import time

from docmirror.models.entities.parse_result import DocumentEntities, ParseResult
from docmirror.models.sealed import seal_parse_result
from docmirror.plugin_api import PluginProvider


def _result() -> ParseResult:
    return ParseResult(entities=DocumentEntities(document_type="business_license"))


def test_provider_discovery_after_seal_does_not_change_facts(monkeypatch):
    from docmirror.plugins._runtime.plugin_registry import PluginRegistry

    class _Projector:
        domain_name = "business_license"
        edition = "enterprise"

        def project(self, sealed):
            return {"fingerprint": sealed.fact_fingerprint()}

    provider = PluginProvider(
        provider_id="chaos",
        version="2",
        projectors=(_Projector(),),
    )
    monkeypatch.setattr(
        "docmirror.plugins._runtime.discovery.load_plugin_providers",
        lambda: [provider],
    )
    sealed = seal_parse_result(_result())
    before = sealed.fact_fingerprint()
    registry = PluginRegistry()

    assert registry.get_projector("business_license", "enterprise") is provider.projectors[0]
    assert sealed.fact_fingerprint() == before
    assert sealed.verify_integrity()


def test_commercial_projector_failures_do_not_change_sealed_facts(monkeypatch):
    from docmirror.server import output_builder

    sealed = seal_parse_result(_result())
    before = sealed.fact_fingerprint()

    def broken(_sealed, _edition):
        raise RuntimeError("projector boom")

    monkeypatch.setattr(output_builder, "build_extended_output", broken)
    outputs = output_builder.build_all_projections(sealed)

    assert outputs["enterprise"] is None and outputs["finance"] is None
    assert {item["reason"] for item in outputs["edition_availability"].values()} == {"projector_failed"}
    assert sealed.fact_fingerprint() == before
    assert sealed.verify_integrity()


def test_commercial_projector_timeouts_do_not_change_sealed_facts(monkeypatch):
    from docmirror.server import output_builder

    sealed = seal_parse_result(_result())
    before = sealed.fact_fingerprint()

    def slow(_sealed, _edition):
        time.sleep(0.2)
        return {"edition": _edition}

    monkeypatch.setattr(output_builder, "build_extended_output", slow)
    monkeypatch.setattr(output_builder, "PROJECTOR_TIMEOUT_SECONDS", 0.01)
    outputs = output_builder.build_all_projections(sealed)

    assert outputs["enterprise"] is None and outputs["finance"] is None
    assert {item["reason"] for item in outputs["edition_availability"].values()} == {"projector_timeout"}
    assert sealed.fact_fingerprint() == before
    assert sealed.verify_integrity()
