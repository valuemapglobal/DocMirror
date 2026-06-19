# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for edition JSON access helpers (Architecture A)."""

from __future__ import annotations

from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ResultStatus
from docmirror.server.edition_access import resolve_quality_trust, resolve_sections


def _mirror() -> ParseResult:
    pr = ParseResult(status=ResultStatus.SUCCESS)
    pr.entities = DocumentEntities(document_type="credit_report")
    pr.sections = [{"id": "core_sec", "title": "Core Section", "page_start": 1}]
    return pr


def test_resolve_sections_prefers_edition_over_core():
    mirror = _mirror()
    editions = {
        "enterprise": {
            "data": {"sections": [{"id": "ent_sec", "title": "Enterprise Section", "page_start": 2}]}
        }
    }
    sections = resolve_sections(mirror, editions)
    assert sections[0]["id"] == "ent_sec"


def test_resolve_sections_falls_back_to_core():
    mirror = _mirror()
    assert resolve_sections(mirror, {})[0]["id"] == "core_sec"


def test_resolve_quality_trust_from_edition():
    mirror = _mirror()
    editions = {"community": {"quality": {"trust_score": 0.88, "validation_passed": True}}}
    quality = resolve_quality_trust(mirror, editions)
    assert quality is not None
    assert quality["trust_score"] == 0.88
