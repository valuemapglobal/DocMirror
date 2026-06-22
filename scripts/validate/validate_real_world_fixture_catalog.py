#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Validate the Real-World Fixture Bank catalog."""

from __future__ import annotations

import sys
from pathlib import Path

from docmirror.configs.ga_experience import load_real_world_fixture_bank

REPO_ROOT = Path(__file__).resolve().parent.parent


def validate_real_world_fixture_catalog() -> list[str]:
    data = load_real_world_fixture_bank()
    errors: list[str] = []
    source_types = set(data.get("source_types") or [])
    quality_buckets = set(data.get("quality_buckets") or [])
    fixtures = data.get("fixtures") or []
    seen_sources = {item.get("source_type") for item in fixtures if isinstance(item, dict)}
    seen_buckets = {item.get("quality_bucket") for item in fixtures if isinstance(item, dict)}
    missing_sources = source_types - seen_sources
    missing_buckets = quality_buckets - seen_buckets
    if missing_sources:
        errors.append(f"missing fixture source_types {sorted(missing_sources)}")
    if missing_buckets:
        errors.append(f"missing fixture quality_buckets {sorted(missing_buckets)}")
    ids: set[str] = set()
    for item in fixtures:
        if not isinstance(item, dict):
            errors.append("fixture entry must be a mapping")
            continue
        fixture_id = str(item.get("id") or "")
        if not fixture_id:
            errors.append("fixture missing id")
        elif fixture_id in ids:
            errors.append(f"duplicate fixture id {fixture_id}")
        ids.add(fixture_id)
        if item.get("source_type") not in source_types:
            errors.append(f"{fixture_id}: invalid source_type {item.get('source_type')!r}")
        if item.get("quality_bucket") not in quality_buckets:
            errors.append(f"{fixture_id}: invalid quality_bucket {item.get('quality_bucket')!r}")
        if not item.get("domain"):
            errors.append(f"{fixture_id}: domain missing")
        if not item.get("support_level"):
            errors.append(f"{fixture_id}: support_level missing")
        if not item.get("expected_outputs"):
            errors.append(f"{fixture_id}: expected_outputs missing")
        path = REPO_ROOT / str(item.get("path") or "")
        if not item.get("private") and not path.is_file():
            errors.append(f"{fixture_id}: fixture path missing: {path}")
    return errors


def main() -> int:
    errors = validate_real_world_fixture_catalog()
    if errors:
        print("Real-World Fixture Bank validation FAILED:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("Real-World Fixture Bank validation OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
