# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Community 6 premium + generic integration extract gates."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from docmirror.input.entry.factory import PerceiveOptions, perceive_document
from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ResultStatus
from docmirror.plugins._runtime.community import (
    community_plugin_module,
    find_premium_community_plugin,
    get_community_premium_domains,
)
from docmirror.plugins._runtime.runner import run_plugin_extract_sync
from tests.contract.test_edition_schema_conformance import check_community

pytestmark = [pytest.mark.integration]

PREMIUM_DOMAINS = get_community_premium_domains()

FIXTURE_BY_DOMAIN: dict[str, Path] = {
    "bank_statement": Path("tests/fixtures/synthetic/bank_ledger_3page_smoke.pdf"),
    "wechat_payment": Path("tests/fixtures/wechat_payment/synthetic_easy_standard.pdf"),
    "alipay_payment": Path("tests/fixtures/alipay_payment/synthetic_easy_standard.pdf"),
    "business_license": Path("tests/fixtures/business_license/synthetic_medium_variant.pdf"),
    "vat_invoice": Path("tests/fixtures/vat_invoice/synthetic_easy_standard.pdf"),
    "credit_report": Path("tests/fixtures/synthetic/credit_report_section_smoke.pdf"),
}


def _mirror(document_type: str) -> ParseResult:
    pr = ParseResult(status=ResultStatus.SUCCESS)
    pr.entities = DocumentEntities(document_type=document_type)
    return pr


@pytest.mark.parametrize("domain", PREMIUM_DOMAINS)
def test_premium_plugin_registered(domain: str):
    plugin, modname = find_premium_community_plugin(domain)
    assert plugin is not None, domain
    assert modname == community_plugin_module(domain)
    assert plugin.domain_name == domain


@pytest.mark.parametrize("domain", PREMIUM_DOMAINS)
def test_premium_community_extract_plugin_name(domain: str):
    out = run_plugin_extract_sync(_mirror(domain), edition="community")
    if out is None:
        pytest.skip(f"no community output for {domain} on minimal mirror")
    if domain in ("alipay_payment", "wechat_payment", "bank_statement"):
        pytest.skip(f"{domain} requires mirror tables for minimal extract")
    assert out["plugin"]["name"] == domain
    assert out["classification"]["matched_document_type"] == domain
    errors = check_community(out)
    assert not errors, errors


def test_unknown_domain_uses_generic_plugin():
    mirror = _mirror("id_card")
    out = run_plugin_extract_sync(mirror, edition="community", full_text="")
    assert out is not None
    assert out["plugin"]["name"] == "generic"
    assert out["classification"]["matched_document_type"] == "id_card"
    assert "community_generic_fallback" in out["status"]["warnings"]
    errors = check_community(out)
    assert not errors, errors


@pytest.mark.parametrize("domain,fixture", FIXTURE_BY_DOMAIN.items())
def test_public_fixture_can_be_perceived(domain: str, fixture: Path):
    assert fixture.exists(), domain
    result = asyncio.run(
        perceive_document(fixture, PerceiveOptions(enhance_mode="standard", max_pages=3))
    )
    assert result.pages, domain
    assert result.full_text or result.total_tables >= 0
