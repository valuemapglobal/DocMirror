# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from docmirror.features.agent.router import route_document
from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ResultStatus
from docmirror.models.sealed import seal_parse_result
from docmirror.server.output_builder import build_community_projection


def test_agent_route_uses_public_core_domain_term():
    route = route_document("bank_statement")
    assert route.community_tier == "core_domain"


def test_community_projection_uses_public_document_type():
    result = ParseResult(status=ResultStatus.SUCCESS)
    result.entities = DocumentEntities(document_type="business_license")

    payload = build_community_projection(seal_parse_result(result))

    assert payload is not None
    assert payload["schema"]["name"] == "docmirror.community"
    assert payload["document"]["type"] == "business_license"
