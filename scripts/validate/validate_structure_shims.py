#!/usr/bin/env python3
"""Validate that the removed ``docmirror/structure`` package stays absent."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STRUCTURE_ROOT = ROOT / "docmirror" / "structure"


def main() -> int:
    if STRUCTURE_ROOT.exists():
        print("Structure removal validation FAILED")
        print(f"  - removed package still exists: {_rel(STRUCTURE_ROOT)}")
        return 1
    print("Structure removal validation OK")
    return 0


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
