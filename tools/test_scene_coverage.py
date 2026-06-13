#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Report classify regression coverage vs scene_keywords.yaml."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SCENE_KEYWORDS = REPO_ROOT / "docmirror" / "configs" / "yaml" / "scene_keywords.yaml"
CLASSIFY_MANIFEST = REPO_ROOT / "docmirror" / "configs" / "yaml" / "test" / "gates" / "classify.yaml"
REGISTRY = REPO_ROOT / "tests" / "fixtures" / "registry.yaml"


def _load_scenes() -> set[str]:
    if not SCENE_KEYWORDS.is_file():
        return set()
    data = yaml.safe_load(SCENE_KEYWORDS.read_text(encoding="utf-8")) or {}
    keywords = data.get("scene_keywords") or data
    return {str(k) for k in keywords.keys()}


def _load_classify_document_types() -> set[str]:
    if not CLASSIFY_MANIFEST.is_file():
        return set()
    data = yaml.safe_load(CLASSIFY_MANIFEST.read_text(encoding="utf-8")) or {}
    types: set[str] = set()
    for case in data.get("cases") or []:
        gates = case.get("gates") or {}
        dt_gate = gates.get("document_type") or {}
        if "equals" in dt_gate:
            types.add(str(dt_gate["equals"]))
    return types


def _load_registry_types() -> set[str]:
    if not REGISTRY.is_file():
        return set()
    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    types: set[str] = set()
    for asset in data.get("assets") or []:
        if asset.get("document_type"):
            types.add(str(asset["document_type"]))
    return types


def main() -> int:
    scenes = _load_scenes()
    classify_types = _load_classify_document_types()
    registry_types = _load_registry_types()
    covered = classify_types | registry_types

    total = len(scenes)
    covered_count = len(covered & scenes)
    missing = sorted(scenes - covered)

    print("Classify regression coverage report")
    print(f"  scene_keywords total: {total}")
    print(f"  covered by classify.yaml + registry: {covered_count}")
    print(f"  coverage ratio: {covered_count / max(total, 1):.1%}")
    if covered:
        print(f"  covered scenes: {', '.join(sorted(covered & scenes))}")
    if missing:
        print(f"  not yet covered ({len(missing)}): showing first 20")
        for scene in missing[:20]:
            print(f"    - {scene}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
