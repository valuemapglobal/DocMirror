# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
TQG manifest loader — parses YAML gate specifications into executable cases.

Reads track manifests from ``configs/yaml/test/gates/`` and produces
``TQGCase`` dataclass instances with file paths, tier labels, gate specs, and
optional environment overrides. Supports loading individual tracks or the full
manifest corpus for batch runners.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from docmirror.configs.paths import YAML_DIR

TQG_GATES_DIR = YAML_DIR / "test" / "gates"
TQG_ROOT = YAML_DIR / "test"


@dataclass
class TQGCase:
    id: str
    track: str
    layer: str = ""
    tier: str = "regression"
    fixture: Path | None = None
    pipeline: str = "perceive"
    options: dict[str, Any] = field(default_factory=dict)
    gates: dict[str, Any] = field(default_factory=dict)
    oracle: dict[str, Any] | None = None
    tier_tags: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    failure_class: str | None = None
    editions: list[str] = field(default_factory=list)
    optional_edition: bool = False
    gate_profile: str | None = None
    skip_if_fixture_missing: bool = True

    @property
    def is_slow(self) -> bool:
        return "slow" in self.tier_tags or self.tier == "slow"


def _resolve_fixture(raw: str, repo_root: Path | None = None) -> Path:
    root = repo_root or Path.cwd()
    path = Path(raw)
    if not path.is_absolute():
        if raw.startswith("tests/"):
            path = root / raw
        else:
            path = root / "tests" / raw
    return path


def _case_from_entry(entry: dict[str, Any], *, track: str, layer: str, repo_root: Path) -> TQGCase:
    fixture_raw = entry.get("fixture")
    fixture = _resolve_fixture(fixture_raw, repo_root) if fixture_raw else None
    return TQGCase(
        id=str(entry["id"]),
        track=track,
        layer=layer or entry.get("layer", ""),
        tier=str(entry.get("tier", "regression")),
        fixture=fixture,
        pipeline=str(entry.get("pipeline", "perceive")),
        options=dict(entry.get("options") or {}),
        gates=dict(entry.get("gates") or {}),
        oracle=entry.get("oracle"),
        tier_tags=list(entry.get("tier_tags") or []),
        tags=list(entry.get("tags") or []),
        failure_class=entry.get("failure_class"),
        editions=list(entry.get("editions") or []),
        optional_edition=bool(entry.get("optional_edition", False)),
        gate_profile=entry.get("gate_profile"),
        skip_if_fixture_missing=bool(entry.get("skip_if_fixture_missing", True)),
    )


def load_track_manifest(path: Path, *, repo_root: Path | None = None) -> list[TQGCase]:
    root = repo_root or Path.cwd()
    if not path.is_file():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    track = str(data.get("track", path.stem))
    layer = str(data.get("layer", ""))
    cases: list[TQGCase] = []
    for entry in data.get("cases") or []:
        if not isinstance(entry, dict) or "id" not in entry:
            continue
        cases.append(_case_from_entry(entry, track=track, layer=layer, repo_root=root))
    return cases


def load_all_manifests(*, repo_root: Path | None = None) -> list[TQGCase]:
    root = repo_root or Path.cwd()
    cases: list[TQGCase] = []
    if not TQG_GATES_DIR.is_dir():
        return cases
    for path in sorted(TQG_GATES_DIR.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        cases.extend(load_track_manifest(path, repo_root=root))
    return cases


def validate_manifest_file(path: Path, *, repo_root: Path | None = None) -> list[str]:
    """Return validation errors for a manifest file."""
    errors: list[str] = []
    root = repo_root or Path.cwd()
    try:
        cases = load_track_manifest(path, repo_root=root)
    except Exception as exc:
        return [f"{path}: parse error: {exc}"]
    if not cases and path.name != "_template.yaml":
        errors.append(f"{path}: no cases defined")
    for case in cases:
        if case.fixture and not case.fixture.is_file():
            errors.append(f"{case.id}: fixture missing: {case.fixture}")
        if not case.gates and not case.gate_profile and case.pipeline != "metadata_only":
            oracle = case.oracle or {}
            oracle_only = bool(
                oracle
                and (
                    oracle.get("audit")
                    or oracle.get("column_fidelity")
                    or oracle.get("quarantine_metadata")
                    or oracle.get("text_snapshot")
                    or oracle.get("mirror_structure")
                    or oracle.get("mirror_conservation")
                    or oracle.get("mirror_geometry")
                    or oracle.get("scanned_micro_grid")
                    or oracle.get("scanned_local_structure")
                    or oracle.get("page_canvas")
                    or oracle.get("pcm_finance")
                    or oracle.get("bank_statement")
                    or oracle.get("mode")
                )
            )
            if not oracle_only:
                errors.append(f"{case.id}: empty gates")
        if not case.id:
            errors.append(f"{path}: case missing id")
    return errors
