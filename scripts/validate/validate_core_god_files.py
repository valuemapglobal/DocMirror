#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Fail CI when protected pipeline modules become new or larger god files.

The historical gate scanned the removed monolithic core package. An empty scan
therefore reported success. This gate
protects the real fact-pipeline and projection packages, rejects an empty scan,
and treats existing hotspots as a shrink-only baseline.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCMIRROR = ROOT / "docmirror"
GOD_LOC = 800

PROTECTED_ROOTS = (
    DOCMIRROR / "evidence",
    DOCMIRROR / "framework",
    DOCMIRROR / "input",
    DOCMIRROR / "models",
    DOCMIRROR / "output",
    DOCMIRROR / "plugins",
    DOCMIRROR / "server",
    DOCMIRROR / "tables",
    DOCMIRROR / "topology",
)

# Existing debt is accepted only at or below this exact baseline. New modules
# above GOD_LOC fail and every listed module is expected to shrink over time.
SHRINK_ONLY_BASELINE: dict[str, int] = {
    "docmirror.evidence.plane": 2669,
    "docmirror.input.extraction.extractor": 1975,
    "docmirror.input.extraction.scanned_table_reconstructor": 1142,
    "docmirror.models.entities.parse_result": 1074,
    "docmirror.models.mirror.core": 1040,
    "docmirror.output.community_bundle": 1076,
    "docmirror.plugins._base.generic_community_adapter": 2665,
    "docmirror.plugins._base.kv_community_enrich": 844,
    "docmirror.plugins._runtime.post_extract.hooks.community_business": 1145,
    "docmirror.plugins.credit_report.business_records": 1124,
    "docmirror.plugins.credit_report.repayment_grid": 1160,
    "docmirror.plugins.credit_report.scanned_business": 1080,
    "docmirror.tables.engine": 1035,
    "docmirror.topology.page": 1644,
    "docmirror.topology.reconstructors": 1201,
}


def _module_name(path: Path) -> str:
    rel = path.relative_to(ROOT).with_suffix("")
    return ".".join(rel.parts)


def main() -> int:
    offenders: list[tuple[str, int]] = []
    scanned: list[Path] = []
    for protected_root in PROTECTED_ROOTS:
        if not protected_root.is_dir():
            print(f"ERROR: protected root missing: {protected_root.relative_to(ROOT)}", file=sys.stderr)
            return 1
        scanned.extend(protected_root.rglob("*.py"))
    if not scanned:
        print("ERROR: protected source scan is empty", file=sys.stderr)
        return 1

    for path in scanned:
        if "__pycache__" in path.parts:
            continue
        n = sum(1 for _ in path.open(encoding="utf-8"))
        if n <= GOD_LOC:
            continue
        mod = _module_name(path)
        baseline = SHRINK_ONLY_BASELINE.get(mod)
        if baseline is None or n > baseline:
            offenders.append((mod, n))

    if offenders:
        for mod, n in sorted(offenders, key=lambda x: -x[1]):
            print(f"ERROR: god file {mod} ({n} LOC > {GOD_LOC})", file=sys.stderr)
        print("Existing hotspots are shrink-only; update code, not the baseline.", file=sys.stderr)
        return 1

    print(
        f"Protected god-file gate OK ({len(scanned)} modules scanned, {len(SHRINK_ONLY_BASELINE)} shrink-only hotspots)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
