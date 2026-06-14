#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Fail CI when new core god files appear (CPA design 12 §7.2)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "docmirror" / "core"
GOD_LOC = 800

# All known large modules split (ADR-CPA-08). Empty allowlist = strict gate.
ALLOWLIST: set[str] = set()


def _module_name(path: Path) -> str:
    rel = path.relative_to(ROOT).with_suffix("")
    return ".".join(rel.parts)


def main() -> int:
    offenders: list[tuple[str, int]] = []
    for path in CORE.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        n = sum(1 for _ in path.open(encoding="utf-8"))
        if n <= GOD_LOC:
            continue
        mod = _module_name(path)
        if mod not in ALLOWLIST:
            offenders.append((mod, n))

    if offenders:
        for mod, n in sorted(offenders, key=lambda x: -x[1]):
            print(f"ERROR: god file {mod} ({n} LOC > {GOD_LOC})", file=sys.stderr)
        print(
            f"Allowlisted (pending split): {', '.join(sorted(ALLOWLIST))}",
            file=sys.stderr,
        )
        return 1

    print(f"Core god-file gate OK (allowlist {len(ALLOWLIST)} modules > {GOD_LOC} LOC)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
