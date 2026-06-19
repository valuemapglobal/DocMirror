# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Architecture A contract gate tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ResultStatus
from docmirror.plugins.composition import CompositionReason
from docmirror.plugins.post_extract.runner import run_post_extract_hooks
from docmirror.server.output_builder import build_all_projections


def test_mirror_snapshot_before_editions():
    result = ParseResult(status=ResultStatus.SUCCESS)
    result.entities = DocumentEntities(document_type="business_license")
    order: list[str] = []

    def _extended(*args, **kwargs):
        ed = args[1] if len(args) > 1 else kwargs.get("edition", "unknown")
        order.append(ed)
        return {"edition": ed}

    with patch.object(ParseResult, "to_api_dict", side_effect=lambda **_kw: order.append("mirror") or {"data": {}}):
        with patch("docmirror.server.output_builder.build_community_output", side_effect=lambda *_a, **_k: order.append("community") or {"edition": "community"}):
            with patch("docmirror.server.output_builder.build_extended_output", side_effect=_extended):
                with patch("docmirror.server.output_builder._edition_package_available", return_value=True):
                    build_all_projections(result)

    assert order[0] == "mirror"
    assert order[1] == "community"
    assert set(order[2:]) == {"enterprise", "finance"}


def test_post_extract_does_not_require_mirror_mutation():
    result = ParseResult(status=ResultStatus.SUCCESS)
    extracted = {"edition": "community", "data": {}}
    before_pages = len(result.pages)

    hook = MagicMock()
    hook.apply = MagicMock()

    with patch(
        "docmirror.plugins.post_extract.runner.resolve_post_extract_hooks",
        return_value=[],
    ):
        run_post_extract_hooks(
            result,
            extracted=extracted,
            edition="community",
            document_type="bank_statement",
        )

    assert len(result.pages) == before_pages


def test_composition_reason_on_license_degrade():
    from docmirror.plugins.composition import apply_license_degrade

    plugin = MagicMock(domain_name="bank_statement")
    out = apply_license_degrade({"edition": "community", "status": {"warnings": []}}, edition="enterprise", plugin=plugin)
    assert out["composition"]["reason"] == CompositionReason.LICENSE_DEGRADE.value
    assert out["composition"]["source_edition"] == "community"


def test_extended_projection_has_composition_reason():
    result = ParseResult(status=ResultStatus.SUCCESS)
    result.entities = DocumentEntities(document_type="business_license")

    with patch("docmirror.server.output_builder.build_community_output", return_value={"edition": "community"}):
        with patch(
            "docmirror.server.output_builder.build_extended_output",
            return_value={"edition": "enterprise", "metadata": {}, "status": {"warnings": []}},
        ):
            with patch("docmirror.server.output_builder._edition_package_available", return_value=True):
                outputs = build_all_projections(result, editions=("enterprise",))

    assert outputs["enterprise"] is not None
    assert outputs["enterprise"]["composition"]["reason"] == CompositionReason.INDEPENDENT_EXTRACT.value
