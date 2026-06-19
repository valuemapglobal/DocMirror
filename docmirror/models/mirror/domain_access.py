# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Parse-time SSOT helpers — read structures from `_page_evidence_bundles`."""

from __future__ import annotations

from typing import Any

from docmirror.core.ocr.page_canvas.evidence_bundles import (
    bundle_evidence_items,
    local_structure_evidence_pages_from_bundles,
)


def local_structure_evidence_pages_from_domain_specific(
    domain_specific: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Return evidence-shaped pages with field_grid structures from page bundles."""
    return local_structure_evidence_pages_from_bundles(domain_specific)


def micro_grid_evidence_pages_from_domain_specific(
    domain_specific: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Return all micro-grid OCR evidence pages (forensic export / OCR pools)."""
    return [
        evidence
        for evidence in bundle_evidence_items(domain_specific, bundle_key="micro_grid_evidence")
        if evidence.get("lines")
    ]


def raw_micro_grid_evidence_from_domain_specific(
    domain_specific: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Return raw micro-grid OCR evidence (lines/tokens) for forensic OCR pools."""
    return bundle_evidence_items(domain_specific, bundle_key="micro_grid_evidence")


def raw_local_structure_evidence_from_domain_specific(
    domain_specific: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Return raw local-structure OCR evidence (lines/tokens) for forensic OCR pools."""
    return bundle_evidence_items(domain_specific, bundle_key="local_structure_evidence")
