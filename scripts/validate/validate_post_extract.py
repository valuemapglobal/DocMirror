# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Validate post_extract hooks against importable modules."""

from __future__ import annotations

import sys

from docmirror.plugins._runtime.post_extract.catalog import get_hook_class, load_post_extract_catalog


def validate_post_extract() -> list[str]:
    errors: list[str] = []
    catalog = load_post_extract_catalog()
    if not catalog:
        errors.append("post_extract.yaml loaded empty or missing")
        return errors
    for hook_id, spec in catalog.items():
        if not spec.module:
            errors.append(f"{hook_id}: missing module")
            continue
        try:
            get_hook_class(spec)
        except Exception as exc:
            errors.append(f"{hook_id}: cannot import {spec.module}.{spec.class_name}: {exc}")
    return errors


def main() -> int:
    errors = validate_post_extract()
    if errors:
        print("Post-extract validation FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print("Post-extract validation OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
