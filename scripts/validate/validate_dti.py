# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Validate DTI + classification scene maps (design 09)."""

from __future__ import annotations

import sys

from docmirror.configs.classification.rules_loader import categories_with_scene_maps
from docmirror.configs.validators.dti import load_business_scenes, validate_business_scenes


def main() -> int:
    scenes = load_business_scenes()
    if not scenes:
        print("WARN: scene_keywords empty or missing")
        return 0

    errors: list[str] = []
    mapped = categories_with_scene_maps()
    all_mapped: list[str] = []
    for cat_id, scene_list in mapped.items():
        all_mapped.extend(scene_list)
        unknown = validate_business_scenes(scene_list)
        for u in unknown:
            errors.append(f"category {cat_id!r} maps_to_scenes unknown scene {u!r}")

    print(
        f"DTI validation OK: {len(scenes)} business_scenes, "
        f"{len(mapped)} categories with maps_to_scenes, "
        f"{len(all_mapped)} mapped links"
    )
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
