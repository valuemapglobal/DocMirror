# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Community 6 premium + generic integration extract gates."""

from __future__ import annotations

import asyncio
import importlib
from pathlib import Path

import pytest

from docmirror.configs.domain.registry import get_canonical_premium_domains
from docmirror.framework.middlewares.extraction.community_fact_recognizer import run_canonical_enrichment
from docmirror.input.entry.factory import PerceiveOptions, perceive_document
from docmirror.input.entry.options import normalize_parse_policy
from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ResultStatus
from docmirror.models.schemas.registry import validate_projection_payload
from docmirror.server.output_builder import build_community_projection

pytestmark = [pytest.mark.integration]

PREMIUM_DOMAINS = get_canonical_premium_domains()

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
def test_premium_capability_is_core_owned(domain: str):
    capability = importlib.import_module(f"docmirror.plugins.{domain}.community_plugin").plugin
    assert capability.domain_name == domain


@pytest.mark.parametrize("domain", PREMIUM_DOMAINS)
def test_premium_recognizer_returns_fact_patch(domain: str):
    patch = run_canonical_enrichment(_mirror(domain))

    assert patch.capability_id == domain
    assert patch.document_type in {None, domain}


def test_unknown_domain_uses_generic_plugin():
    mirror = _mirror("id_card")
    patch = run_canonical_enrichment(mirror, full_text="")

    assert patch.capability_id == "generic"
    assert "community_generic_fallback" in patch.warnings


@pytest.mark.parametrize("domain,fixture", FIXTURE_BY_DOMAIN.items())
def test_public_fixture_can_be_perceived(domain: str, fixture: Path):
    assert fixture.exists(), domain
    result = asyncio.run(
        perceive_document(
            fixture,
            PerceiveOptions(policy=normalize_parse_policy(enhance_mode="standard", max_pages=3)),
        )
    )
    view = result.to_read_view()
    assert view.pages, domain
    assert view.full_text or view.total_tables >= 0
    output = build_community_projection(
        result,
        file_path=str(fixture),
    )
    assert output is not None, domain
    assert set(output) == {"schema", "document", "sections", "datasets", "files", "warnings"}
    assert output["sections"], domain
    assert validate_projection_payload("community", output).valid, domain
