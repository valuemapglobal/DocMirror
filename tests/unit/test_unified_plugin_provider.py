# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from docmirror.configs.domain.registry import (
    CANONICAL_DOMAIN_IDS,
    get_canonical_domain_manifest,
    list_canonical_domain_manifests,
)
from docmirror.plugin_api import PluginProvider
from docmirror.plugins._runtime.plugin_registry import PluginRegistry


class _Projector:
    domain_name = "custom_document"
    edition = "enterprise"
    display_name = "Custom Enterprise"

    def project(self, result):
        return {"edition": self.edition, "fingerprint": result.fact_fingerprint()}


def _provider(provider_id: str = "third-party") -> PluginProvider:
    return PluginProvider(
        provider_id=provider_id,
        version="2.0.0",
        projectors=(_Projector(),),
    )


def test_provider_registry_owns_projectors_only():
    registry = PluginRegistry()
    registry._discovered = True
    provider = _provider()

    registry.register_provider(provider)

    assert registry.get_projector("custom_document", "enterprise") is provider.projectors[0]
    assert registry.list_providers() == (provider,)
    assert registry.list_domains() == {"custom_document": ["enterprise"]}


def test_provider_rejects_pre_seal_recognizer_contract():
    with pytest.raises(ValidationError, match="recognizers"):
        PluginProvider.model_validate(
            {
                "provider_id": "legacy",
                "version": "1",
                "recognizers": [object()],
                "projectors": [_Projector()],
            }
        )


def test_provider_requires_a_projector():
    with pytest.raises(ValidationError, match="at least one projector"):
        PluginProvider(provider_id="empty", version="2")


def test_extended_output_uses_registered_projector_with_sealed_result():
    from docmirror.models.entities.parse_result import DocumentEntities, ParseResult
    from docmirror.models.sealed import SealedParseResult, seal_parse_result
    from docmirror.server.output_builder import build_extended_output

    observed: list[object] = []

    class _EnterpriseProjector:
        domain_name = "custom_document"
        edition = "enterprise"

        def project(self, result):
            observed.append(result)
            view = result.to_read_view()
            return {"edition": self.edition, "document": {"document_type": view.entities.document_type}}

    sealed = seal_parse_result(ParseResult(entities=DocumentEntities(document_type="custom_document")))
    projector = _EnterpriseProjector()
    with patch(
        "docmirror.plugins._runtime.plugin_registry.registry.get_projector",
        return_value=projector,
    ):
        output = build_extended_output(sealed, "enterprise")

    assert output is not None
    assert output["edition"] == "enterprise"
    assert output["document"]["document_type"] == "custom_document"
    assert output["composition"]["reason"] == "independent_extract"
    assert isinstance(observed[0], SealedParseResult)


def test_extended_output_rejects_mutable_parse_result():
    from docmirror.models.entities.parse_result import ParseResult
    from docmirror.server.output_builder import build_extended_output

    with pytest.raises(TypeError, match="SealedParseResult"):
        build_extended_output(ParseResult(), "enterprise")


def test_registry_freezes_after_discovery(monkeypatch):
    registry = PluginRegistry()
    monkeypatch.setattr(
        "docmirror.plugins._runtime.discovery.load_plugin_providers",
        lambda: [],
    )
    registry._ensure_discovered()
    with pytest.raises(RuntimeError, match="frozen"):
        registry.register_provider(_provider("late"))


def test_pluggy_is_discovery_transport_for_provider_hook(monkeypatch):
    from docmirror.plugins._runtime import discovery

    provider = _provider("entry-point")

    class _Hook:
        @staticmethod
        def docmirror_plugin_provider():
            return [provider]

    class _Manager:
        hook = _Hook()

    monkeypatch.setattr(discovery, "get_plugin_manager", lambda: _Manager())
    assert discovery.load_plugin_providers() == [provider]


def test_bundled_domains_are_post_seal_plugin_providers(monkeypatch):
    monkeypatch.setattr(
        "docmirror.plugins._runtime.discovery.load_plugin_providers",
        lambda: [],
    )
    registry = PluginRegistry()

    assert {provider.provider_id for provider in registry.list_providers()} == {
        f"bundled.{domain}" for domain in CANONICAL_DOMAIN_IDS
    }
    assert set(CANONICAL_DOMAIN_IDS) == {
        "alipay_payment",
        "bank_statement",
        "business_license",
        "credit_report",
        "generic",
        "vat_invoice",
        "wechat_payment",
    }
    assert len(list_canonical_domain_manifests()) == 7


def test_bank_canonical_resources_are_wheel_safe_package_data():
    plugin_root = files("docmirror.plugins.bank_statement")
    core_root = files("docmirror.configs.domain")
    manifest = get_canonical_domain_manifest("bank_statement")

    assert manifest is not None
    assert manifest["resources"]["key_synonyms"] == "resources/bank_statement/key_synonyms.yaml"
    assert plugin_root.joinpath("plugin.yaml").is_file()
    assert plugin_root.joinpath("resources").joinpath("institutions.yaml").is_file()
    assert core_root.joinpath("resources").joinpath("bank_statement").joinpath("key_synonyms.yaml").is_file()


def test_business_resource_ssots_are_not_duplicated_in_core_configs():
    forbidden = (
        "docmirror/configs/yaml/classification_rules.yaml",
        "docmirror/configs/yaml/document_field_schemas.yaml",
        "docmirror/configs/yaml/domain_contracts/community_core.yaml",
        "docmirror/configs/yaml/institution_registry.yaml",
        "docmirror/configs/yaml/key_synonyms.yaml",
        "docmirror/configs/yaml/layout_profiles.yaml",
        "docmirror/configs/yaml/ocr_corrections.yaml",
        "docmirror/configs/yaml/plugin_capability.yaml",
        "docmirror/configs/yaml/scene_keywords.yaml",
    )
    assert not [path for path in forbidden if Path(path).exists()]


def test_retired_post_extract_catalog_is_absent():
    assert not Path("docmirror/configs/yaml/post_extract.yaml").exists()
