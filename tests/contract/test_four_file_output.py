# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Product contract tests — four-file output separation (04 CLI redesign)."""

from __future__ import annotations

import importlib

import pytest

pytestmark = [pytest.mark.tier_contract]

from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ResultStatus
from docmirror.server.edition_outputs import build_all_edition_outputs
from tests.contract.test_edition_schema_conformance import check_community

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


def test_generic_community_envelope_conforms():
    from docmirror.plugins.generic.community_plugin import plugin

    mirror = ParseResult(status=ResultStatus.SUCCESS)
    mirror.entities = DocumentEntities(document_type="id_card")
    mirror.entities.domain_specific = {"name": "测试", "id_number": "110101199001011234"}

    out = plugin.extract_from_mirror(mirror)
    errors = check_community(out)
    assert errors == [], f"generic envelope errors: {errors}"
    assert out["plugin"]["name"] == "generic"
    assert out["document"]["archetype"] == "generic_mirror"


def test_mirror_only_envelope_for_enterprise_only_type():
    from docmirror.plugins.runner import run_plugin_extract_sync

    result = _minimal_mirror("audit_report")
    out = run_plugin_extract_sync(result, edition="community")
    assert out is not None
    assert "mirror_only:no_community_plugin" in out["status"]["warnings"]
    assert out.get("mirror_ref", {}).get("document_type") == "audit_report"


def test_generic_envelope_for_demoted_type():
    from docmirror.plugins.runner import run_plugin_extract_sync

    result = _minimal_mirror("id_card")
    result.entities.domain_specific = {"name": "张三"}
    out = run_plugin_extract_sync(result, edition="community")
    assert out is not None
    assert out["plugin"]["name"] == "generic"
    assert out["document"]["archetype"] == "generic_mirror"
    assert "community_generic_fallback" in out["status"]["warnings"]
    assert not check_community(out)


def test_generic_fallback_envelope_for_demoted_type():
    from docmirror.plugins.runner import run_plugin_extract_sync

    result = _minimal_mirror("id_card")
    result.entities.domain_specific = {"name": "ZhangSan"}
    out = run_plugin_extract_sync(result, edition="community")
    assert out is not None
    assert out["plugin"]["name"] == "generic"
    assert out["classification"]["matched_document_type"] == "id_card"
    assert "community_generic_fallback" in out["status"]["warnings"]


def test_perceive_result_envelope_no_edition_on_mirror():
    from docmirror.core.entry.perceive_result import PerceiveResult

    mirror = _minimal_mirror()
    env = PerceiveResult(mirror=mirror, editions={"community": {"edition": "community"}})
    assert env.mirror is mirror
    assert env.editions["community"]["edition"] == "community"
    assert "_edition_outputs" not in (mirror.entities.domain_specific or {})
