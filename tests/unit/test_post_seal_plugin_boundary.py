from __future__ import annotations

import importlib.util

import pytest

from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ResultStatus
from docmirror.models.sealed import seal_parse_result
from docmirror.plugin_api import PluginProvider
from docmirror.plugins._runtime.plugin_registry import PluginRegistry


def _sealed(document_type: str = "id_card"):
    result = ParseResult(
        status=ResultStatus.SUCCESS,
        entities=DocumentEntities(
            document_type=document_type,
            domain_specific={"name": "测试", "id_number": "110101199001011234"},
        ),
    )
    return result, seal_parse_result(result)


def test_bundled_community_plugin_runs_only_from_sealed_snapshot() -> None:
    mutable, sealed = _sealed()
    registry = PluginRegistry()
    projector = registry.get_projector("generic", "community", sealed_schema=sealed.schema_version)

    assert projector is not None
    with pytest.raises(TypeError, match="SealedParseResult"):
        projector.project(mutable)

    before = sealed.integrity_fingerprint
    payload = projector.project(sealed)

    assert payload is not None
    assert payload["document"]["type"] == "id_card"
    assert sealed.integrity_fingerprint == before
    assert sealed.verify_integrity()
    assert sealed.to_read_view().entities.domain_specific == {
        "name": "测试",
        "id_number": "110101199001011234",
    }


def test_all_editions_share_one_post_seal_plugin_registry(monkeypatch) -> None:
    class _EnterpriseProjector:
        domain_name = "bank_statement"
        edition = "enterprise"

        def project(self, result):
            return {"edition": self.edition, "fingerprint": result.fact_fingerprint()}

    class _FinanceProjector(_EnterpriseProjector):
        edition = "finance"

    enterprise = _EnterpriseProjector()
    finance = _FinanceProjector()
    monkeypatch.setattr(
        "docmirror.plugins._runtime.discovery.load_plugin_providers",
        lambda: [
            PluginProvider(
                provider_id="test.commercial",
                version="1",
                projectors=(enterprise, finance),
            )
        ],
    )
    registry = PluginRegistry()

    assert registry.list_domains() == {
        "alipay_payment": ["community"],
        "bank_statement": ["community", "enterprise", "finance"],
        "business_license": ["community"],
        "credit_report": ["community"],
        "generic": ["community"],
        "vat_invoice": ["community"],
        "wechat_payment": ["community"],
    }
    assert registry.get_projector("bank_statement", "community") is not None
    assert registry.get_projector("bank_statement", "enterprise") is enterprise
    assert registry.get_projector("bank_statement", "finance") is finance


@pytest.mark.parametrize(
    "module",
    (
        "docmirror.framework.middlewares.extraction.community_fact_recognizer",
        "docmirror.input.canonical.fact_patch",
        "docmirror.ocr.local_structure.candidate_supplement",
        "docmirror.ocr.micro_grid.materialize",
    ),
)
def test_pre_seal_plugin_bridges_are_retired(module: str) -> None:
    assert importlib.util.find_spec(module) is None
