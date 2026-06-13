# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Product contract tests — four-file output separation (04 CLI redesign)."""

from __future__ import annotations

import importlib

import pytest

pytestmark = [pytest.mark.tier_contract]

from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ResultStatus
from docmirror.server.edition_outputs import build_all_edition_outputs

_FORBIDDEN_MIRROR_KEYS = frozenset({"records", "mirror_ref", "edition"})


def _minimal_mirror(document_type: str = "business_license") -> ParseResult:
    pr = ParseResult(status=ResultStatus.SUCCESS)
    pr.entities = DocumentEntities(document_type=document_type)
    return pr


def test_mirror_output_has_no_plugin_records():
    result = _minimal_mirror()
    outputs = build_all_edition_outputs(result, full_text="")
    mirror = outputs["mirror"]
    # Mirror API must not embed edition plugin payloads
    assert "editions" not in mirror.get("data", {})
    assert "mirror_ref" not in mirror


def test_community_mirror_document_type_consistency():
    result = _minimal_mirror("business_license")
    outputs = build_all_edition_outputs(result)
    comm = outputs.get("community")
    if comm is None:
        pytest.skip("no community output")
    mirror_type = outputs["mirror"].get("data", {}).get("document", {}).get("document_type")
    comm_type = comm.get("document", {}).get("document_type")
    assert comm_type == mirror_type or comm_type == "business_license"


def test_enterprise_not_generated_when_package_missing():
    try:
        importlib.import_module("docmirror_enterprise")
    except ImportError:
        outputs = build_all_edition_outputs(_minimal_mirror())
        assert outputs["enterprise"] is None
        return
    pytest.skip("docmirror_enterprise installed — skip missing-package assertion")


def test_mirror_only_envelope_for_enterprise_only_type():
    from docmirror.plugins.runner import run_plugin_extract_sync

    result = _minimal_mirror("audit_report")
    out = run_plugin_extract_sync(result, edition="community")
    assert out is not None
    assert "mirror_only:no_community_plugin" in out["status"]["warnings"]
    assert out.get("mirror_ref", {}).get("document_type") == "audit_report"


def test_perceive_result_envelope_no_edition_on_mirror():
    from docmirror.core.perceive_result import PerceiveResult

    mirror = _minimal_mirror()
    env = PerceiveResult(mirror=mirror, editions={"community": {"edition": "community"}})
    assert env.mirror is mirror
    assert env.editions["community"]["edition"] == "community"
    assert "_edition_outputs" not in (mirror.entities.domain_specific or {})
