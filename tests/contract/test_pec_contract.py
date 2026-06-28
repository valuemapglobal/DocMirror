# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""PEC contract tests — any DomainPlugin must satisfy runner invariants."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = [pytest.mark.tier_contract]

from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ResultStatus
from docmirror.plugins._runtime.runner import run_plugin_extract_sync


class FakeEnterprisePlugin:
    domain_name = "bank_statement"
    display_name = "Fake Bank"
    edition = "enterprise"
    requires_license = False

    async def extract(self, document_context: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": "2.0",
            "data": {"records": [{"amount": 1}], "summary": {"total_rows": 1}},
            "status": {"success": True, "warnings": [], "errors": []},
            "quality": {"trust_score": 0.9, "confidence": 0.95, "validation_passed": True},
        }


def _mirror(document_type: str = "bank_statement") -> ParseResult:
    pr = ParseResult(status=ResultStatus.SUCCESS)
    pr.entities = DocumentEntities(document_type=document_type)
    return pr


def test_pec_invariants_on_fake_enterprise_plugin():
    mirror = _mirror()
    with patch("docmirror.plugins.runner._edition_package_available", return_value=True):
        with patch("docmirror.plugins.registry.get", return_value=FakeEnterprisePlugin()):
            out = run_plugin_extract_sync(mirror, edition="enterprise")
    assert out is not None
    assert out["edition"] == "enterprise"
    assert out["data"]["summary"]["total_rows"] >= 1


def test_pec_trust_projection_enriches_edition_only():
    mirror = _mirror()
    with patch("docmirror.plugins.runner._edition_package_available", return_value=True):
        with patch("docmirror.plugins.registry.get", return_value=FakeEnterprisePlugin()):
            out = run_plugin_extract_sync(mirror, edition="enterprise")
    assert out is not None
    assert out.get("quality", {}).get("trust_score") == pytest.approx(0.9)
    assert mirror.trust is None
