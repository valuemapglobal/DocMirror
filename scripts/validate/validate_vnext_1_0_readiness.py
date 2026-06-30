#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Validate the vNext 1.0 readiness gate.

This is intentionally a thin orchestrator over existing focused validators.
It gives release work one fast command that proves the vNext mainline is still:

- free of removed PageProjection/PageCanvas imports and raw references,
- covered by the TQG manifest,
- bounded by Mirror volume checks,
- backed by metadata-only UDTR golden contracts,
- ready for private cross-format samples when available.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ReadinessStep:
    name: str
    argv: tuple[str, ...]


STEPS: tuple[ReadinessStep, ...] = (
    ReadinessStep("TQG manifest", ("python3", "scripts/validate/validate_test_manifest.py")),
    ReadinessStep("vNext removed refs", ("python3", "scripts/validate/gate_vnext_removed_refs.py")),
    ReadinessStep("vNext removed imports", ("python3", "scripts/validate/validate_vnext_removed_imports.py")),
    ReadinessStep("vNext mirror volume", ("python3", "scripts/validate/gate_vnext_mirror_volume.py")),
    ReadinessStep(
        "UDTR metadata golden",
        ("python3", "scripts/validate/validate_udtr_golden.py", "tests/golden/udtr/manifest.example.json"),
    ),
    ReadinessStep(
        "UDTR cross-format matrix",
        (
            "python3",
            "scripts/validate/run_udtr_cross_format_matrix.py",
            "tests/golden/udtr/cross_format_real_manifest.example.json",
        ),
    ),
)


def main() -> int:
    failed: list[str] = []
    for step in STEPS:
        print(f"[vNext 1.0] {step.name} ...", flush=True)
        result = subprocess.run(step.argv, cwd=REPO_ROOT, check=False)
        if result.returncode != 0:
            failed.append(step.name)

    if failed:
        print("vNext 1.0 readiness FAILED:", file=sys.stderr)
        for name in failed:
            print(f"  - {name}", file=sys.stderr)
        return 1

    print("vNext 1.0 readiness OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
