#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Validate middleware_catalog.yaml vs enhancement_profiles.yaml (MEP SSOT)."""

from __future__ import annotations

import sys

from docmirror.configs.middleware.catalog import validate_catalog


def main() -> int:
    errors = validate_catalog()
    if errors:
        print("MEP catalog validation FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print("MEP catalog validation OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
