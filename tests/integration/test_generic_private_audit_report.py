# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Private Generic audit-report gate against the canonical facts and Bundle v3."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from docmirror.input.entry.factory import PerceiveOptions, perceive_document
from docmirror.input.entry.options import ParsePolicy
from docmirror.models.schemas.registry import validate_projection_payload
from docmirror.server.output_builder import build_community_projection

pytestmark = [pytest.mark.integration, pytest.mark.slow, pytest.mark.tier_slow, pytest.mark.track_e2e]
FIXTURE = Path("tests/fixtures-private/2.杭州华英新塘2024年度审计报告_cleaned.pdf")


def test_generic_private_audit_report_canonical_and_v3_contract() -> None:
    if not FIXTURE.exists():
        pytest.skip("private Generic audit-report fixture is unavailable")
    sealed = asyncio.run(
        perceive_document(FIXTURE, PerceiveOptions(policy=ParsePolicy(mode="balanced", ocr="off")))
    )
    result = sealed.to_read_view()
    payload = build_community_projection(sealed, file_path=str(FIXTURE))

    assert result.entities.document_type == "audit_report"
    assert result.pages and len(result.pages) > 10
    assert payload is not None
    assert payload["document"]["type"] == "audit_report"
    assert payload["sections"]
    assert validate_projection_payload("community", payload).valid
    assert sum(dataset["row_count"] for dataset in payload["datasets"]) > 0
