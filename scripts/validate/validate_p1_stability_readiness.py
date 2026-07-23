#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Validate the aggregate evidence required to call the P1 core stable."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
STABILITY = ROOT / "docmirror/configs/stability/stability_evidence.json"
GOLDEN = ROOT / "docmirror/configs/stability/ga_6plus1.yaml"
PERFORMANCE = ROOT / "docmirror/configs/stability/performance_baseline.yaml"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def validate_manifest() -> list[str]:
    errors: list[str] = []
    evidence = _load_json(STABILITY)
    if evidence.get("schema_version") != "docmirror.stability_evidence.v1":
        errors.append("unexpected stability evidence schema_version")
    required_gates = {
        "core_contract_freeze",
        "ga_6plus1",
        "worker_determinism",
        "performance_rss",
        "plugin_chaos",
        "external_plugin_install",
    }
    gates = evidence.get("gates")
    if not isinstance(gates, dict) or set(gates) != required_gates:
        errors.append("stability evidence must contain exactly the six P1 gate records")
    return errors


def qualification_errors() -> list[str]:
    errors = validate_manifest()
    evidence = _load_json(STABILITY)
    if evidence.get("status") != "qualified":
        errors.append("aggregate stability evidence status is not qualified")

    gates = evidence.get("gates") or {}
    for gate in (
        "core_contract_freeze",
        "ga_6plus1",
        "worker_determinism",
        "performance_rss",
        "plugin_chaos",
        "external_plugin_install",
    ):
        if gates.get(gate) != "qualified":
            errors.append(f"gate {gate} is not qualified")

    golden = _load_yaml(GOLDEN)
    for case in golden.get("cases") or []:
        fingerprint = str(case.get("expected_fact_fingerprint") or "")
        if len(fingerprint) != 64 or fingerprint == "PENDING_BASELINE":
            errors.append(f"Golden case {case.get('id')} has no frozen fact fingerprint")
    performance = _load_yaml(PERFORMANCE)
    if performance.get("status") != "approved":
        errors.append("performance/RSS baseline is not approved")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-only", action="store_true")
    parser.add_argument("--require-qualified", action="store_true")
    args = parser.parse_args(argv)
    errors = validate_manifest()
    if args.require_qualified:
        errors = qualification_errors()
        contract = subprocess.run(
            [sys.executable, "scripts/validate/validate_core_contract_freeze.py", "--require-qualified"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if contract.returncode != 0:
            errors.append("semantic core contract snapshot is not technically qualified")
    if errors:
        print("P1 stability readiness FAILED:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    if args.require_qualified:
        print("P1 core stability QUALIFIED")
    else:
        print("P1 stability evidence manifest OK (qualification may still be pending)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
