# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Collect S5 key-value fields from UMMA page blocks (Design 20 PMCC)."""

from __future__ import annotations

from typing import Any


def collect_kv_fields_from_blocks(mirror: Any) -> dict[str, Any]:
    """Read ``flow.key_values`` from an already projected Mirror payload."""
    from docmirror.models.mirror.vnext_access import pages as vnext_pages
    from docmirror.models.mirror.vnext_access import resolve_ref

    fields: dict[str, Any] = {}
    if not isinstance(mirror, dict):
        return fields

    for page in vnext_pages(mirror):
        if not isinstance(page, dict):
            continue
        page_num = int(page.get("page_number") or 0)
        for block in page.get("blocks") or []:
            if not isinstance(block, dict):
                continue
            if block.get("morphology") != "S5":
                continue
            ref = str(block.get("ref") or "")
            if not ref.startswith("kv:"):
                continue
            kv = resolve_ref(mirror, page_num, ref)
            if not isinstance(kv, dict):
                continue
            key = str(kv.get("key") or "").strip()
            val = str(kv.get("value") or "").strip()
            if key and val and key not in fields:
                fields[key] = val
    return fields
