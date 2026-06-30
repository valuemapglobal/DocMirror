# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Public test fixture hygiene for the vNext release suite."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
GATE_DIR = ROOT / "docmirror" / "configs" / "yaml" / "test" / "gates"


def _fixture_path(value: str) -> Path:
    path = Path(value)
    if value.startswith("fixtures/"):
        return ROOT / "tests" / path
    return ROOT / path


def test_gate_fixtures_are_public_or_explicitly_skipped():
    offenders: list[str] = []
    for manifest in sorted(GATE_DIR.glob("*.yaml")):
        data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        for case in data.get("cases") or []:
            fixture = case.get("fixture")
            if not fixture:
                continue
            if not _fixture_path(str(fixture)).exists() and not case.get("skip_if_fixture_missing"):
                offenders.append(f"{manifest.relative_to(ROOT)}:{case.get('id')}:{fixture}")
    assert offenders == []


def test_public_tests_do_not_hardcode_local_absolute_paths():
    offenders: list[str] = []
    for path in sorted((ROOT / "tests").rglob("test_*.py")):
        rel = path.relative_to(ROOT)
        if rel.parts[:2] == ("tests", "fixtures-private"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "/" + "Users/" in text:
            offenders.append(str(rel))
    assert offenders == []
