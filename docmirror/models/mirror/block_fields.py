# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Collect S5 key-value fields from UMMA page blocks (Design 20 PMCC)."""

from __future__ import annotations

from typing import Any


def collect_kv_fields_from_blocks(parse_result: Any) -> dict[str, Any]:
    """Read ``flow.key_values`` via ``pages[n].blocks`` S5 refs."""
    if hasattr(parse_result, "sync_page_canvases"):
        parse_result.sync_page_canvases()

    fields: dict[str, Any] = {}
    for page in getattr(parse_result, "pages", []) or []:
        canvas = getattr(page, "page_canvas", None)
        if canvas is None:
            continue
        for block in canvas.blocks:
            if block.morphology != "S5":
                continue
            ref = str(block.ref or "")
            if not ref.startswith("kv:"):
                continue
            try:
                idx = int(ref.split(":", 1)[1])
            except (IndexError, ValueError):
                continue
            kvs = canvas.flow.key_values
            if idx < 0 or idx >= len(kvs):
                continue
            kv = kvs[idx]
            if not isinstance(kv, dict):
                continue
            key = str(kv.get("key") or "").strip()
            val = str(kv.get("value") or "").strip()
            if key and val and key not in fields:
                fields[key] = val
    return fields
