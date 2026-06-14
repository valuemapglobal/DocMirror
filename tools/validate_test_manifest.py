#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Validate TQG manifest YAML — fixture existence and gate schema."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
GATES_DIR = REPO_ROOT / "docmirror" / "configs" / "yaml" / "test" / "gates"

ALLOWED_GATE_KEYS = frozenset(
    {"equals", "in", "min", "max", "max_issues", "contains"}
)

PIPELINES_WITHOUT_FIXTURE = frozenset(
    {
        "transport_capability",
        "transport_dispatch",
        "e2e_four_file",
        "e2e_contract",
        "metadata_only",
        "licensing",
    }
)

# Real document binaries (PII) are local-only — not committed in public OSS repo.
# Synthetic smoke fixtures under tests/fixtures/synthetic/ may be committed.
def _requires_committed_fixture(fixture_raw: str) -> bool:
    normalized = str(fixture_raw).replace("\\", "/")
    if "fixtures/synthetic/" in normalized:
        return True
    if normalized.endswith((".yaml", ".json", ".txt", ".md")):
        return True
    return False


def _validate_gate_spec(gate_name: str, spec: object, case_id: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(spec, dict):
        return [f"{case_id}.{gate_name}: gate spec must be a mapping"]
    if not spec:
        return [f"{case_id}.{gate_name}: empty gate spec"]
    unknown = set(spec.keys()) - ALLOWED_GATE_KEYS
    if unknown:
        errors.append(f"{case_id}.{gate_name}: unknown keys {sorted(unknown)}")
    return errors


def validate_manifest_file(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return [f"{path}: parse error: {exc}"]

    cases = data.get("cases") or []
    if not cases and not path.name.startswith("_"):
        errors.append(f"{path}: no cases defined")

    for entry in cases:
        if not isinstance(entry, dict):
            errors.append(f"{path}: invalid case entry")
            continue
        case_id = str(entry.get("id", "<missing-id>"))
        if "id" not in entry:
            errors.append(f"{path}: case missing id")

        fixture_raw = entry.get("fixture")
        pipeline = entry.get("pipeline", "perceive")
        if fixture_raw:
            fixture = Path(fixture_raw)
            if not fixture.is_absolute():
                if str(fixture_raw).startswith("tests/"):
                    fixture = REPO_ROOT / fixture_raw
                else:
                    fixture = REPO_ROOT / "tests" / fixture_raw
            if not fixture.is_file():
                if _requires_committed_fixture(fixture_raw):
                    errors.append(f"{case_id}: fixture missing: {fixture}")
        elif pipeline not in PIPELINES_WITHOUT_FIXTURE and not path.name.startswith("_"):
            pass  # fixture optional for transport/e2e contract pipelines

        gates = entry.get("gates") or {}
        oracle = entry.get("oracle") or {}
        oracle_only = bool(
            oracle
            and (
                oracle.get("audit")
                or oracle.get("column_fidelity")
                or oracle.get("quarantine_metadata")
                or oracle.get("text_snapshot")
                or oracle.get("mode")
            )
        )
        if (
            not gates
            and not entry.get("gate_profile")
            and entry.get("pipeline") != "metadata_only"
            and not oracle_only
        ):
            errors.append(f"{case_id}: empty gates")
        for gate_name, spec in gates.items():
            errors.extend(_validate_gate_spec(gate_name, spec, case_id))

        tier_tags = entry.get("tier_tags") or []
        if entry.get("tier") == "slow" and "slow" not in tier_tags:
            errors.append(f"{case_id}: tier=slow should include tier_tags: [slow]")

    profiles = data.get("profiles") or {}
    for profile_id, profile in profiles.items():
        if not isinstance(profile, dict):
            errors.append(f"{path}: profile {profile_id} must be a mapping")

    return errors


def main() -> int:
    if not GATES_DIR.is_dir():
        print(f"ERROR: gates directory missing: {GATES_DIR}")
        return 1

    all_errors: list[str] = []
    manifest_files = sorted(GATES_DIR.glob("*.yaml"))
    if not manifest_files:
        print(f"ERROR: no manifest files in {GATES_DIR}")
        return 1

    validated = [p.name for p in manifest_files if not p.name.startswith("_")]

    for path in manifest_files:
        if path.name.startswith("_"):
            continue
        errors = validate_manifest_file(path)
        all_errors.extend(errors)

    if all_errors:
        print("TQG manifest validation FAILED:")
        for err in all_errors:
            print(f"  - {err}")
        return 1

    print(f"TQG manifest validation OK ({len(validated)} files: {', '.join(validated)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
