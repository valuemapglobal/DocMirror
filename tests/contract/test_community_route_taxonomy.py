# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from docmirror.features.agent.router import route_document
from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ResultStatus
from docmirror.server.output_builder import build_community_output


def test_agent_route_uses_public_core_domain_term():
    route = route_document("bank_statement")
    assert route.community_tier == "core_domain"


def test_community_output_metadata_uses_route_taxonomy():
    result = ParseResult(status=ResultStatus.SUCCESS)
    result.entities = DocumentEntities(document_type="business_license")

    payload = build_community_output(result)

    assert payload is not None
    metadata = payload.get("metadata") or {}
    assert metadata["community_tier"] in {"core_domain", "generic_fallback", "enterprise_only"}
    assert metadata["community_tier"] != "premium"
