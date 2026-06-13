#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Sync tests/golden/manifest.json from TQG gate YAML manifests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
GATES_DIR = REPO_ROOT / "docmirror" / "configs" / "yaml" / "test" / "gates"
GOLDEN_MANIFEST = REPO_ROOT / "tests" / "golden" / "manifest.json"


def _fixture_path(raw: str) -> str:
    if raw.startswith("fixtures/"):
        return raw
    return f"fixtures/{raw}"


def _golden_path(fixture: str) -> str:
    return f"../{fixture}"


_TRACK_GOLDEN_SUBDIR = {
    "extract": "extract",
    "classify": "classify",
    "edition": "edition",
    "mirror": "extract",
    "transport": "",
    "e2e": "",
}


def build_cases() -> list[dict]:
    cases: list[dict] = []
    for path in sorted(GATES_DIR.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        track = str(data.get("track", path.stem))
        golden_subdir = _TRACK_GOLDEN_SUBDIR.get(track, "")
        for entry in data.get("cases") or []:
            if not isinstance(entry, dict) or "id" not in entry:
                continue
            fixture_raw = entry.get("fixture") or ""
            fixture = _fixture_path(str(fixture_raw).replace("tests/", ""))
            gates = entry.get("gates") or {}
            dt_gate = gates.get("document_type") or {}
            doc_type = dt_gate.get("equals")
            case_row = {
                "id": f"{track}.{entry['id']}",
                "track": track,
                "case_id": entry["id"],
                "path": _golden_path(fixture) if fixture_raw else None,
                "fixture": fixture if fixture_raw else None,
                "document_type": doc_type,
                "tier": entry.get("tier", "regression"),
                "tier_tags": entry.get("tier_tags") or [],
                "gate_manifest": path.name,
                "pipeline": entry.get("pipeline", "perceive"),
                "tags": entry.get("tags") or [],
            }
            if golden_subdir:
                case_row["golden_subdir"] = golden_subdir
            cases.append(case_row)
    return cases


def main() -> int:
    cases = build_cases()
    payload = {
        "version": 1,
        "description": "TQG case index synced with docmirror/configs/yaml/test/gates/*.yaml",
        "source": "docmirror/configs/yaml/test/gates",
        "cases": cases,
    }
    GOLDEN_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN_MANIFEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(cases)} cases to {GOLDEN_MANIFEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
