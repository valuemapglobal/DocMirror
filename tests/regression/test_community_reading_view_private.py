# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Private real-document gates for the fixed Community Bundle v3 projection."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from docmirror.input.entry.factory import PerceiveOptions, perceive_document
from docmirror.input.entry.options import normalize_parse_policy
from docmirror.models.schemas.registry import validate_projection_payload
from docmirror.server.output_builder import build_community_projection

pytestmark = [pytest.mark.integration, pytest.mark.slow, pytest.mark.tier_slow]

_CASES = (
    ("bank_statement", Path("tests/fixtures-private/bank_statement"), "*_银行流水_*.pdf", 3),
    ("wechat_payment", Path("tests/fixtures-private/wechat_payment"), "*微信流水*.pdf", 3),
    ("alipay_payment", Path("tests/fixtures-private/alipay_payment"), "*.pdf", 3),
    ("vat_invoice", Path("tests/fixtures-private/vat_invoice"), "*.pdf", 2),
    ("business_license", Path("tests/fixtures-private/business_license"), "营业执照_*.jpg", 1),
)


@pytest.mark.parametrize("domain,fixture_dir,pattern,max_pages", _CASES, ids=[case[0] for case in _CASES])
def test_real_document_projects_to_community_v3(
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
            PerceiveOptions(
                policy=normalize_parse_policy(
                    enhance_mode="standard",
                    max_pages=max_pages,
                    doc_type_hint=f"{domain}:force",
                )
            ),
        )
    )
    payload = build_community_projection(result, file_path=str(fixture))

    assert payload is not None
    assert set(payload) == {"schema", "document", "sections", "datasets", "files", "warnings"}
    assert payload["sections"]
    assert validate_projection_payload("community", payload).valid
