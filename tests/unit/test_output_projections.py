# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for ParseResult SSOT projection builder."""

from __future__ import annotations

from unittest.mock import patch

from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ResultStatus
from docmirror.server.output_builder import build_all_projections


def _mirror(document_type: str = "business_license") -> ParseResult:
    pr = ParseResult(status=ResultStatus.SUCCESS)
    pr.entities = DocumentEntities(document_type=document_type)
    return pr


def test_build_all_projections_serializes_mirror_before_editions():
    result = _mirror()
    call_order: list[str] = []

    def _community(*_args, **_kwargs):
        call_order.append("community")
        return {"edition": "community", "metadata": {}}

    def _extended(_result, edition, *_args, **_kwargs):
        call_order.append(edition)
        return {"edition": edition, "metadata": {}}

    def _mirror_dict(**_kwargs):
        call_order.append("mirror")
        return {"data": {"document": {}}}

    with patch("docmirror.server.output_builder.build_community_output", side_effect=_community):
        with patch("docmirror.server.output_builder.build_extended_output", side_effect=_extended):
            with patch("docmirror.server.output_builder._edition_package_available", return_value=True):
                with patch.object(ParseResult, "to_api_dict", side_effect=_mirror_dict):
                    outputs = build_all_projections(result)

    assert call_order == ["mirror", "community", "enterprise", "finance"]
    assert outputs["mirror"]["data"]["document"] == {}
    assert outputs["community"]["edition"] == "community"


def test_build_all_projections_single_to_api_dict_call():
    result = _mirror()
    with patch("docmirror.server.output_builder.build_community_output", return_value=None):
        with patch("docmirror.server.output_builder._edition_package_available", return_value=False):
            with patch.object(
                ParseResult,
                "to_api_dict",
                return_value={"data": {}},
            ) as mirror_mock:
                build_all_projections(result, request_id="req-1")

    mirror_mock.assert_called_once_with(
        include_text=False,
        mirror_level="standard",
        request_id="req-1",
    )
