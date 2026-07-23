# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Private credit-report subtype coverage for canonical facts and Bundle v3."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from docmirror.input.entry.factory import PerceiveOptions, perceive_document
from docmirror.input.entry.options import normalize_parse_policy
from docmirror.models.schemas.registry import validate_projection_payload
from docmirror.server.output_builder import build_community_projection

pytestmark = [pytest.mark.integration, pytest.mark.slow, pytest.mark.tier_slow]
_FIXTURE_DIR = Path("tests/fixtures-private/credit_report")


def _cases(pattern: str, subtype: str, public_type: str) -> list[pytest.ParameterSet]:
    fixtures = sorted(_FIXTURE_DIR.glob(pattern))
    if not fixtures:
        return [pytest.param(Path("__missing__"), subtype, public_type, marks=pytest.mark.skip)]
    return [pytest.param(path, subtype, public_type, id=f"{subtype}-{index}") for index, path in enumerate(fixtures, 1)]


CASES = [
    *_cases("*_个人简版征信报告.pdf", "personal_brief", "personal_credit_report_brief"),
    *_cases("*_个人详版征信报告.pdf", "personal_detail", "personal_credit_report_detailed"),
    *_cases("*_企业征信*.pdf", "enterprise", "enterprise_credit_report"),
]


@pytest.mark.parametrize("fixture,subtype,public_type", CASES)
def test_credit_report_subtype_projects_complete_v3(
    fixture: Path,
    subtype: str,
    public_type: str,
) -> None:
    sealed = asyncio.run(
        perceive_document(
            fixture,
            PerceiveOptions(
                policy=normalize_parse_policy(
                    enhance_mode="standard",
                    doc_type_hint="credit_report:force",
                )
            ),
        )
    )
    result = sealed.to_read_view()
    payload = build_community_projection(sealed, file_path=str(fixture))
    assert "report_subtype" not in result.entities.domain_specific
    assert payload is not None
    assert payload["document"]["type"] == public_type
    assert validate_projection_payload("community", payload).valid
    assert payload["sections"]
    assert any(dataset["row_count"] > 0 for dataset in payload["datasets"])
