# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Contract checks for supported compatibility surfaces awaiting retirement."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
REGISTER = ROOT / "docmirror" / "configs" / "architecture" / "compatibility_retirement.yaml"


def _load_register() -> dict:
    return yaml.safe_load(REGISTER.read_text(encoding="utf-8")) or {}


def test_compatibility_register_has_major_release_guardrails() -> None:
    register = _load_register()

    assert register["version"] == 1
    assert register["policy"]["removal_not_before"] == "2.0.0"
    requirements = register["policy"]["required_before_removal"]
    assert len(requirements) >= 5
    assert any("deprecation release" in item for item in requirements)
    assert any("major-version" in item for item in requirements)


def test_every_compatibility_surface_has_owner_replacement_and_status() -> None:
    surfaces = _load_register()["surfaces"]
    symbols = [item["symbol"] for item in surfaces]

    assert len(symbols) == len(set(symbols))
    assert symbols
    for item in surfaces:
        assert item["owner"]
        assert item["replacement"]
        assert item["status"] in {"supported_compatibility", "retained_data_compatibility"}


def test_legacy_community_business_modules_are_quarantined_to_compatibility() -> None:
    register = _load_register()
    modules = register["compatibility_only_modules"]

    assert {item["module"] for item in modules} == {
        "docmirror.plugins._runtime.post_extract.hooks.community_business",
        "docmirror.plugins._runtime.post_extract.hooks.community_precision",
    }
    assert all(item["reachable_via"].endswith("build_community_output") for item in modules)

    production_sources = [
        path
        for path in (ROOT / "docmirror").rglob("*.py")
        if path.as_posix() != (ROOT / "docmirror/server/output_builder.py").as_posix()
    ]
    assert not [
        path
        for path in production_sources
        if "build_community_output" in path.read_text(encoding="utf-8")
    ]
