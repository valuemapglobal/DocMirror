# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Private real-document gates for the unified Community reading view."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from docmirror.input.entry.factory import PerceiveOptions, perceive_document
from docmirror.models.schemas.registry import validate_projection_payload
from docmirror.plugins._runtime.runner import clear_run_cache
from docmirror.server.output_builder import build_community_output
from tests._community_reading import assert_community_reading_view

pytestmark = [pytest.mark.integration, pytest.mark.slow, pytest.mark.tier_slow]

_CASES = (
    (
        "bank_statement",
        Path("tests/fixtures-private/bank_statement"),
        "*_银行流水_*.pdf",
        3,
    ),
    (
        "wechat_payment",
        Path("tests/fixtures-private/wechat_payment"),
        "*微信流水*.pdf",
        3,
    ),
    (
        "alipay_payment",
        Path("tests/fixtures-private/alipay_payment"),
        "*.pdf",
        3,
    ),
    (
        "vat_invoice",
        Path("tests/fixtures-private/vat_invoice"),
        "*.pdf",
        2,
    ),
    (
        "business_license",
        Path("tests/fixtures-private/business_license"),
        "营业执照_*.jpg",
        1,
    ),
)


@pytest.mark.parametrize("domain,fixture_dir,pattern,max_pages", _CASES, ids=[case[0] for case in _CASES])
def test_real_document_reading_view_contract(
    domain: str,
    fixture_dir: Path,
    pattern: str,
    max_pages: int,
) -> None:
    fixture = next(iter(sorted(fixture_dir.glob(pattern))), None)
    if fixture is None:
        pytest.skip(f"private fixture unavailable: {domain}")
    result = asyncio.run(
        perceive_document(
            fixture,
            PerceiveOptions(enhance_mode="standard", max_pages=max_pages),
        )
    )
    result.entities.document_type = domain
    clear_run_cache()
    output = build_community_output(result, result.full_text or "", file_path=str(fixture))

    assert output is not None
    assert output["plugin"]["name"] == domain
    assert validate_projection_payload("community", output).valid is True
    assert output["data"]["document_flow"]
    assert_community_reading_view(output["data"])
