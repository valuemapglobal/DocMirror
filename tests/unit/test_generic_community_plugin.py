# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Generic community plugin tests."""

from __future__ import annotations

from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ResultStatus
from docmirror.plugins.generic.community_plugin import plugin


def _mirror(document_type: str, domain_specific: dict | None = None) -> ParseResult:
    pr = ParseResult(status=ResultStatus.SUCCESS)
    pr.entities = DocumentEntities(
        document_type=document_type,
        domain_specific=domain_specific or {},
    )
    return pr


def test_generic_plugin_domain_name():
    assert plugin.domain_name == "generic"
    assert plugin.edition == "community"


def test_id_card_classified_produces_generic_output():
    out = plugin.extract_from_mirror(
        _mirror("id_card", {"name": "张三", "id_number": "110101199001011234"})
    )
    assert out["schema_version"] == "2.0"
    assert out["plugin"]["name"] == "generic"
    assert out["plugin"]["support_level"] == "generic"
    assert out["classification"]["matched_document_type"] == "id_card"
    assert out["document"]["document_type"] == "id_card"
    assert out["data"]["fields"]["name"] == "张三"
    assert "community_generic_fallback" in out["status"]["warnings"]


def test_generic_output_collects_key_values():
    pr = _mirror("payroll_slip")
    kv = type("KV", (), {"key": "姓名", "value": "李四", "confidence": 1.0, "bbox": None, "evidence_ids": None})()
    page = type("Page", (), {"key_values": [kv], "tables": [], "texts": [], "page_number": 1, "width": 800, "height": 1000})()
    pr.pages = [page]

    out = plugin.extract_from_mirror(pr)
    assert out["data"]["fields"]["姓名"] == "李四"
