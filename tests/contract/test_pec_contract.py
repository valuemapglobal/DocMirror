# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""EditionProjector contract tests for the only commercial execution path."""

from __future__ import annotations

from unittest.mock import patch

from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ResultStatus
from docmirror.models.sealed import SealedParseResult, seal_parse_result
from docmirror.server.output_builder import build_extended_output


class FakeEnterpriseProjector:
    domain_name = "bank_statement"
    edition = "enterprise"
    requires_license = False

    def __init__(self) -> None:
        self.observed: SealedParseResult | None = None

    def project(self, result: SealedParseResult) -> dict:
        self.observed = result
        return {
            "edition": "enterprise",
            "data": {"records": [{"amount": 1}], "summary": {"total_rows": 1}},
            "status": {"success": True, "warnings": [], "errors": []},
            "quality": {"trust_score": 0.9},
        }


def test_projector_receives_sealed_snapshot_and_cannot_mutate_core() -> None:
    result = ParseResult(status=ResultStatus.SUCCESS)
    result.entities = DocumentEntities(document_type="bank_statement")
    projector = FakeEnterpriseProjector()

    with patch("docmirror.plugins._runtime.plugin_registry.registry.get_projector", return_value=projector):
        output = build_extended_output(seal_parse_result(result), "enterprise")

    assert output is not None
    assert isinstance(projector.observed, SealedParseResult)
    assert output["data"]["summary"]["total_rows"] == 1
    assert output["quality"]["trust_score"] == 0.9
    assert result.trust is None
