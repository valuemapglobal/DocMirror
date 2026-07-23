# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from unittest.mock import patch

import pytest

from docmirror.plugin_api import FactPatch, PluginProvider
from docmirror.plugins._runtime.plugin_registry import PluginRegistry


class _Recognizer:
    provider_id = "third-party"
    domain_name = "custom_document"

    def recognize_facts(self, result, text: str = ""):
        return FactPatch(provider_id=self.provider_id, document_type=self.domain_name)


class _Projector:
    domain_name = "custom_document"
    edition = "community"

    def project(self, result):
        return {"edition": self.edition, "fingerprint": result.fact_fingerprint()}


def test_one_provider_registry_owns_recognizer_and_projector_roles():
    registry = PluginRegistry()
    registry._discovered = True
    recognizer = _Recognizer()
    projector = _Projector()
    provider = PluginProvider(
        provider_id="third-party",
        version="1.2.3",
        recognizers=(recognizer,),
        projectors=(projector,),
    )

    registry.register_provider(provider)

    assert registry.get_recognizer("custom_document") is recognizer
    assert registry.get_projector("custom_document", "community") is projector
    assert registry.list_providers() == (provider,)


def test_extended_output_uses_registered_projector_with_sealed_result():
    from docmirror.models.entities.parse_result import DocumentEntities, ParseResult
    from docmirror.models.sealed import SealedParseResult
    from docmirror.server.output_builder import build_extended_output

    observed: list[object] = []

    class _EnterpriseProjector:
        domain_name = "custom_document"
        edition = "enterprise"

        def project(self, result):
            observed.append(result)
            return {"edition": self.edition, "document": {"document_type": result.entities.document_type}}

    result = ParseResult(entities=DocumentEntities(document_type="custom_document"))
    projector = _EnterpriseProjector()
    with patch(
        "docmirror.plugins._runtime.plugin_registry.registry.get_projector",
        return_value=projector,
    ):
        with patch("docmirror.plugins._runtime.runner.run_plugin_extract_sync") as legacy_runner:
            output = build_extended_output(result, "enterprise")

    assert output is not None
    assert output["edition"] == "enterprise"
    assert output["document"]["document_type"] == "custom_document"
    assert output["composition"]["reason"] == "independent_extract"
    assert isinstance(observed[0], SealedParseResult)
    legacy_runner.assert_not_called()


def test_registry_freezes_after_discovery():
    registry = PluginRegistry()
    registry._ensure_discovered()
    with pytest.raises(RuntimeError, match="frozen"):
        registry.register_provider(PluginProvider(provider_id="late", version="1"))


def test_legacy_metadata_registration_is_not_an_execution_fallback():
    from docmirror.plugins.generic.community_plugin import GenericCommunityPlugin

    registry = PluginRegistry()
    registry._discovered = True
    registry.register(GenericCommunityPlugin())

    assert registry.get("generic", "community") is not None
    assert registry.get_recognizer("generic") is None


def test_pluggy_is_discovery_transport_for_provider_hook(monkeypatch):
    from docmirror.plugins._runtime import discovery

    provider = PluginProvider(provider_id="entry-point", version="1")

    class _Hook:
        @staticmethod
        def docmirror_plugin_provider():
            return [provider]

    class _Manager:
        hook = _Hook()

    monkeypatch.setattr(discovery, "get_plugin_manager", lambda: _Manager())
    assert discovery.load_plugin_providers() == [provider]


def test_builtin_bank_provider_is_loaded_from_package_manifest():
    registry = PluginRegistry()

    plugin = registry.get("bank_statement", "community")
    manifest = registry.get_provider_manifest("bank_statement")

    assert plugin is not None
    assert registry.get_recognizer("bank_statement") is plugin
    assert manifest is not None
    assert manifest["provider"]["implementation"] == "docmirror.plugins.bank_statement.community_plugin:plugin"
    assert manifest["resources"].items() >= {
        "table_styles": "resources/table_styles.yaml",
        "institution_overrides": "resources/institution_overrides.yaml",
        "institutions": "resources/institutions.yaml",
        "key_synonyms": "resources/key_synonyms.yaml",
    }.items()


def test_bank_manifest_resources_are_wheel_safe_package_data():
    plugin_root = files("docmirror.plugins.bank_statement")

    assert plugin_root.joinpath("plugin.yaml").is_file()
    assert plugin_root.joinpath("resources").joinpath("table_styles.yaml").is_file()
    assert plugin_root.joinpath("resources").joinpath("institution_overrides.yaml").is_file()
    assert plugin_root.joinpath("resources").joinpath("institutions.yaml").is_file()
    assert plugin_root.joinpath("resources").joinpath("key_synonyms.yaml").is_file()


def test_all_builtin_community_plugins_own_a_manifest():
    registry = PluginRegistry()
    manifests = registry.list_provider_manifests()

    assert {manifest["provider"]["id"] for manifest in manifests} == {
        "alipay_payment",
        "bank_statement",
        "business_license",
        "credit_report",
        "generic",
        "vat_invoice",
        "wechat_payment",
    }
    assert len(registry.list_providers()) == 7


def test_plugin_manifest_resources_exist_without_importing_implementations():
    plugin_root = files("docmirror").joinpath("plugins")
    registry = PluginRegistry()

    for manifest in registry.list_provider_manifests():
        provider_id = manifest["provider"]["id"]
        provider_root = plugin_root.joinpath(provider_id)
        for resource_path in (manifest.get("resources") or {}).values():
            assert provider_root.joinpath(*str(resource_path).split("/")).is_file(), (provider_id, resource_path)


def test_business_resource_ssots_are_not_kept_in_core_configs():
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


def test_bank_specific_middleware_was_removed_from_core():
    assert not Path("docmirror/framework/middlewares/detection/institution_detector.py").exists()
    assert not Path("docmirror/framework/middlewares/extraction/entity_extractor.py").exists()
    assert not Path("docmirror/layout/scene/institution_hint.py").exists()


def test_generic_plugin_owns_cross_domain_classification_and_table_semantics():
    registry = PluginRegistry()
    manifest = registry.get_provider_manifest("generic")
    assert manifest is not None
    assert manifest["resources"]["classification_rules"] == "resources/classification_rules.yaml"
    resource = files("docmirror.plugins.generic").joinpath("resources/layout_profiles.yaml")
    text = resource.read_text(encoding="utf-8")
    for section in ("table_header_vocabulary:", "table_semantics:", "summary_fields:", "value_type_patterns:"):
        assert section in text


def test_core_classification_and_community_projection_have_no_premium_domain_branches():
    concrete_domains = (
        "alipay_payment",
        "bank_statement",
        "business_license",
        "credit_report",
        "vat_invoice",
        "wechat_payment",
    )
    for relative_path in (
        "docmirror/layout/scene/evidence_engine.py",
        "docmirror/output/community_bundle.py",
    ):
        source = Path(relative_path).read_text(encoding="utf-8")
        assert not [domain for domain in concrete_domains if domain in source], relative_path


def test_generic_post_extract_catalog_contains_no_domain_guard():
    source = Path("docmirror/configs/yaml/post_extract.yaml").read_text(encoding="utf-8")
    assert "document_type ==" not in source
