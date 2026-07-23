# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Smoke coverage for the post-seal projector registry."""

from __future__ import annotations

import pytest

from docmirror.configs.domain.registry import get_canonical_premium_domains
from docmirror.plugin_api import PluginProvider
from docmirror.plugins import PluginRegistry

pytestmark = [pytest.mark.tier_smoke]


class _Projector:
    domain_name = "smoke_document"
    edition = "enterprise"
    display_name = "Smoke Enterprise"

    def project(self, result):
        return {"edition": self.edition, "fingerprint": result.fact_fingerprint()}


def test_bundled_domains_use_the_unified_post_seal_registry(monkeypatch) -> None:
    monkeypatch.setattr(
        "docmirror.plugins._runtime.discovery.load_plugin_providers",
        lambda: [],
    )
    registry = PluginRegistry()

    assert len(get_canonical_premium_domains()) == 6
    assert len(registry.list_providers()) == 7
    assert registry.get_projector("bank_statement", "community") is not None
    assert registry.get_projector("bank_statement", "enterprise") is None


def test_provider_registration_owns_projector_role() -> None:
    registry = PluginRegistry()
    registry._discovered = True
    projector = _Projector()

    registry.register_provider(
        PluginProvider(
            provider_id="smoke",
            version="2",
            projectors=(projector,),
        )
    )

    assert registry.get_projector("smoke_document", "enterprise") is projector
    assert registry.list_domains()["smoke_document"] == ["enterprise"]


def test_unknown_projector_is_absent(monkeypatch) -> None:
    monkeypatch.setattr(
        "docmirror.plugins._runtime.discovery.load_plugin_providers",
        lambda: [],
    )
    registry = PluginRegistry()

    assert registry.get_projector("nonexistent_domain", "enterprise") is None
