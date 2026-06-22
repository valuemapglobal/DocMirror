#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Validate support_matrix.yaml against the Format Capability Registry."""

from __future__ import annotations

import sys

from docmirror.configs.format.loader import load_format_registry
from docmirror.configs.support_matrix import load_support_matrix

_VALID_STATUSES = {"ga", "candidate", "fallback", "unsupported"}
_VALID_OUTPUT_LEVELS = {
    "missing",
    "basic",
    "partial",
    "full",
    "structured",
    "forensic",
    "text_structure",
    "container",
}


def validate_support_matrix() -> list[str]:
    errors: list[str] = []
    caps, _, _ = load_format_registry()
    matrix = load_support_matrix()
    formats = matrix.get("formats") or {}

    for cap_id, cap in sorted(caps.items()):
        entry = formats.get(cap_id)
        if not isinstance(entry, dict):
            errors.append(f"{cap_id}: missing support_matrix entry")
            continue
        status = str(entry.get("ga_status") or "")
        if status not in _VALID_STATUSES:
            errors.append(f"{cap_id}: invalid ga_status {status!r}")
        if not entry.get("user_label"):
            errors.append(f"{cap_id}: missing user_label")
        if entry.get("transport") != cap.transport:
            errors.append(f"{cap_id}: transport mismatch support={entry.get('transport')!r} fcr={cap.transport!r}")
        declared_inputs = {str(x).lower() for x in (entry.get("inputs") or [])}
        missing_exts = set(cap.extensions) - declared_inputs
        if missing_exts:
            errors.append(f"{cap_id}: support_matrix inputs missing extensions {sorted(missing_exts)}")
        outputs = entry.get("outputs")
        if not isinstance(outputs, dict):
            errors.append(f"{cap_id}: missing outputs map")
        else:
            for name in ("mirror", "markdown", "evidence"):
                level = str(outputs.get(name) or "")
                if level not in _VALID_OUTPUT_LEVELS:
                    errors.append(f"{cap_id}: invalid outputs.{name}={level!r}")
        if cap.status == "unsupported" and status != "unsupported":
            errors.append(f"{cap_id}: FCR unsupported but support status is {status!r}")
        if (
            cap.binding
            and cap.binding.transcode
            and cap.binding.transcode.tool != "internal"
            and not entry.get("requires_converter")
            and status == "fallback"
        ):
            errors.append(f"{cap_id}: fallback transcode capability should declare requires_converter")

    extra = set(formats) - set(caps)
    for cap_id in sorted(extra):
        errors.append(f"{cap_id}: support_matrix entry has no FCR capability")
    return errors


def main() -> int:
    errors = validate_support_matrix()
    if errors:
        print("Support Matrix validation FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print("Support Matrix validation OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
