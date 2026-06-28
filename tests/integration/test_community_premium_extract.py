# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Community 6 premium + generic integration extract gates."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from docmirror.input.entry.factory import PerceiveOptions, perceive_document
from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ResultStatus
from docmirror.plugins._runtime.community import get_community_premium_domains
from docmirror.plugins._runtime.community import community_plugin_module, find_premium_community_plugin
from docmirror.plugins._runtime.runner import run_plugin_extract_sync
from tests.contract.test_edition_schema_conformance import check_community

pytestmark = [pytest.mark.integration]

PREMIUM_DOMAINS = get_community_premium_domains()

FIXTURE_BY_DOMAIN: dict[str, Path] = {
    "bank_statement": Path("tests/fixtures/bank_statement/银行流水_中国建设银行_20231226.pdf"),
    "wechat_payment": Path("tests/fixtures/wechat_payment/DemoUser+微信流水.pdf"),
    "alipay_payment": Path("tests/fixtures/alipay_payment/DemoUser+支付宝流水.pdf"),
    "business_license": Path("tests/fixtures/business_license/林晓彤_营业执照_20220826.jpg"),
    "vat_invoice": Path("tests/fixtures/vat_invoice"),
    "credit_report": Path("tests/fixtures/synthetic/credit_report_section_smoke.pdf"),
}

ID_CARD_FIXTURE = Path("tests/fixtures/id_card/ZhangSan_身份证_1976112.pdf")


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


def test_id_card_fixture_uses_generic_plugin():
    if not ID_CARD_FIXTURE.is_file():
        pytest.skip(f"missing fixture {ID_CARD_FIXTURE}")

    perceive_result = asyncio.run(
        perceive_document(ID_CARD_FIXTURE, PerceiveOptions(enhance_mode="standard"))
    )
    mirror = perceive_result.mirror
    assert getattr(mirror.entities, "document_type", "") == "id_card"

    out = run_plugin_extract_sync(mirror, edition="community", full_text=mirror.full_text)
    assert out is not None
    assert out["plugin"]["name"] == "generic"
    assert out["classification"]["matched_document_type"] == "id_card"
    assert "community_generic_fallback" in out["status"]["warnings"]
    errors = check_community(out)
    assert not errors, errors


@pytest.mark.parametrize("domain", PREMIUM_DOMAINS)
def test_premium_fixture_extract_smoke(domain: str):
    fixture = FIXTURE_BY_DOMAIN.get(domain)
    if fixture is None or not fixture.exists():
        pytest.skip(f"no fixture for {domain}")

    if fixture.is_dir():
        candidates = list(fixture.glob("*.pdf")) + list(fixture.glob("*.jpg"))
        if not candidates:
            pytest.skip(f"empty fixture dir for {domain}")
        fixture = candidates[0]

    perceive_result = asyncio.run(
        perceive_document(fixture, PerceiveOptions(enhance_mode="standard", max_pages=3))
    )
    mirror = perceive_result.mirror
    out = run_plugin_extract_sync(mirror, edition="community", full_text=mirror.full_text)
    assert out is not None, domain
    assert out["plugin"]["name"] == domain, domain
    data = out.get("data", {})
    has_content = (
        bool(data.get("fields"))
        or data.get("summary", {}).get("total_rows", 0) > 0
        or bool(data.get("sections"))
    )
    assert has_content, f"{domain}: expected fields, sections, or records from fixture"
