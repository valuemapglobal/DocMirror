# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for ParseResult SSOT projection builder."""

from __future__ import annotations

import logging
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

    def _mirror_result(*_args, **_kwargs):
        call_order.append("mirror")
        return {"mirror": {"schema_version": "3.0.0"}, "document": {}}

    with patch("docmirror.server.output_builder.build_community_output", side_effect=_community):
        with patch("docmirror.server.output_builder.build_extended_output", side_effect=_extended):
            with patch("docmirror.models.mirror.core.MirrorCoreVNext.process", side_effect=_mirror_result):
                outputs = build_all_projections(result, mirror_schema="unsupported_schema")

    assert call_order[0] == "mirror"
    assert call_order[1] == "community"
    assert set(call_order[2:]) == {"enterprise", "finance"}
    assert outputs["mirror"]["mirror"]["schema_version"] == "3.0.0"
    assert outputs["community"]["edition"] == "community"


def test_build_all_projections_single_vnext_mirror_call():
    result = _mirror()
    with patch("docmirror.server.output_builder.build_community_output", return_value=None):
        with patch("docmirror.server.output_builder.build_extended_output", return_value=None):
            with patch(
                "docmirror.models.mirror.core.MirrorCoreVNext.process",
                return_value={"mirror": {}, "document": {}},
            ) as mirror_mock:
                build_all_projections(result, request_id="req-1", mirror_schema="unsupported_schema")

    mirror_mock.assert_called_once()
    assert result._runtime_mirror_cache == {"mirror": {}, "document": {}}
    assert not hasattr(result, "mirror")


def test_build_all_projections_maps_mirror_level_to_vnext_profile():
    result = _mirror()
    with patch("docmirror.server.output_builder.build_community_output", return_value=None):
        with patch("docmirror.server.output_builder.build_extended_output", return_value=None):
            with patch(
                "docmirror.models.mirror.core.MirrorCoreVNext.process",
                return_value={"mirror": {}, "document": {}},
            ) as mirror_mock:
                build_all_projections(result, mirror_level="forensic", editions=())

    options = mirror_mock.call_args.kwargs["options"]
    assert options.profile == "forensic"


def test_build_all_projections_maps_compact_to_canonical_compact_profile():
    result = _mirror()
    with patch("docmirror.server.output_builder.build_community_output", return_value=None):
        with patch("docmirror.server.output_builder.build_extended_output", return_value=None):
            with patch(
                "docmirror.models.mirror.core.MirrorCoreVNext.process",
                return_value={"mirror": {}, "document": {}},
            ) as mirror_mock:
                build_all_projections(result, mirror_level="compact", editions=())

    options = mirror_mock.call_args.kwargs["options"]
    assert options.profile == "canonical_compact"


def test_build_all_projections_can_read_mirror_schema_from_runtime_config(monkeypatch):
    result = _mirror()
    monkeypatch.setenv("DOCMIRROR_MIRROR_SCHEMA", "unsupported_schema")

    with patch("docmirror.server.output_builder.serialize_dmir", return_value={"dmir_version": "test"}):
        with patch(
            "docmirror.models.mirror.core.MirrorCoreVNext.process",
            return_value={"mirror": {"schema_version": "3.0.0"}, "document": {}},
        ) as mirror_mock:
            outputs = build_all_projections(result, editions=())

    mirror_mock.assert_called_once()
    assert outputs["mirror"]["mirror"]["schema_version"] == "3.0.0"


def test_build_all_projections_logs_structured_profile(caplog):
    result = _mirror()
    caplog.set_level(logging.INFO, logger="docmirror.server.output_builder")

    with patch("docmirror.server.output_builder.build_community_output", return_value={"edition": "community"}):
        with patch("docmirror.server.output_builder.build_extended_output", return_value=None):
            build_all_projections(result, editions=("community",))

    assert any(record.__dict__.get("event") == "projection_build" for record in caplog.records)
