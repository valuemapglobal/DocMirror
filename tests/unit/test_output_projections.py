# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for ParseResult SSOT projection builder."""

from __future__ import annotations

import logging
from unittest.mock import patch

from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ResultStatus
from docmirror.models.sealed import seal_parse_result
from docmirror.server.output_builder import build_all_projections


def _mirror(document_type: str = "business_license") -> ParseResult:
    pr = ParseResult(status=ResultStatus.SUCCESS)
    pr.entities = DocumentEntities(document_type=document_type)
    return pr


def test_build_all_projections_serializes_mirror_before_editions():
    result = _mirror()
    call_order: list[str] = []

    def _extended(_result, edition, *_args, **_kwargs):
        call_order.append(edition)
        return {"edition": edition, "metadata": {}}

    def _mirror_result(*_args, **_kwargs):
        call_order.append("mirror")
        return {"mirror": {"schema_version": "3.0.0"}, "document": {}}

    with patch("docmirror.server.output_builder.build_extended_output", side_effect=_extended):
        with patch("docmirror.models.mirror.core.MirrorCoreVNext.process", side_effect=_mirror_result):
            outputs = build_all_projections(seal_parse_result(result))

    assert call_order[0] == "mirror"
    assert "community" not in call_order
    assert set(call_order[1:]) == {"enterprise", "finance"}
    assert outputs["mirror"]["mirror"]["schema_version"] == "3.0.0"
    assert outputs["community"]["schema"]["edition"] == "community"
    assert "dmir" not in outputs


def test_build_all_projections_single_vnext_mirror_call():
    result = _mirror()
    with patch("docmirror.server.output_builder.build_extended_output", return_value=None):
        with patch(
            "docmirror.models.mirror.core.MirrorCoreVNext.process",
            return_value={"mirror": {}, "document": {}},
        ) as mirror_mock:
            build_all_projections(seal_parse_result(result))

    mirror_mock.assert_called_once()
    assert not hasattr(result, "_runtime_mirror_cache")
    assert not hasattr(result, "mirror")


def test_build_all_projections_uses_fixed_standard_mirror_profile():
    result = _mirror()
    with patch("docmirror.server.output_builder.build_extended_output", return_value=None):
        with patch(
            "docmirror.models.mirror.core.MirrorCoreVNext.process",
            return_value={"mirror": {}, "document": {}},
        ) as mirror_mock:
            build_all_projections(seal_parse_result(result))

    options = mirror_mock.call_args.kwargs["options"]
    assert options.profile == "canonical_full"


def test_build_all_projections_logs_structured_profile(caplog):
    result = _mirror()
    caplog.set_level(logging.INFO, logger="docmirror.server.output_builder")

    with patch("docmirror.server.output_builder.build_extended_output", return_value=None):
        build_all_projections(seal_parse_result(result))

    assert any(record.__dict__.get("event") == "projection_build" for record in caplog.records)
