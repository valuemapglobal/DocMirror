#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Run bounded smoke checks for optional dependency extras.

The full ``docmirror[all]`` dependency set is too broad for a fast release
smoke. This script validates extras in small, named groups so a slow or broken
capability is diagnosable.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "docmirror" / "configs" / "release" / "oss_1_0_manifest.yaml"


def _load_manifest() -> dict[str, Any]:
    return yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))


def _wheel_path() -> Path:
    wheels = sorted((REPO_ROOT / "dist").glob("docmirror-*.whl"))
    if not wheels:
        raise SystemExit("No wheel found under dist/. Run python -m build first.")
    return wheels[-1]


def _run(command: list[str], *, cwd: Path | None = None, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd or REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def smoke_extra(extra: str, *, timeout: int) -> tuple[bool, str]:
    root = Path(tempfile.mkdtemp(prefix=f"docmirror-extra-{extra}-"))
    try:
        venv = root / "venv"
        create = _run([sys.executable, "-m", "venv", str(venv)], timeout=60)
        if create.returncode != 0:
            return False, create.stderr or create.stdout

        python = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        docmirror = venv / ("Scripts/docmirror.exe" if sys.platform == "win32" else "bin/docmirror")
        wheel = _wheel_path()
        install = _run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--only-binary=:all:",
                f"{wheel}[{extra}]",
            ],
            timeout=timeout,
        )
        if install.returncode != 0:
            output = install.stderr or install.stdout
            return False, f"install failed for {extra}:\n{output}"

        for command in (
            [str(python), "-c", "import docmirror; print(docmirror.__version__)"],
            [str(docmirror), "doctor"],
        ):
            result = _run(command, timeout=60)
            if result.returncode != 0:
                return False, result.stderr or result.stdout
        return True, f"{extra}: ok"
    except subprocess.TimeoutExpired:
        return False, f"{extra}: timed out after {timeout}s"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke optional DocMirror extras in small groups")
    parser.add_argument(
        "--extras",
        default=None,
        help="Comma-separated extras to smoke. Defaults to release manifest lightweight_extra_smoke.",
    )
    parser.add_argument("--timeout", type=int, default=180, help="Per-extra install timeout in seconds")
    args = parser.parse_args()

    manifest = _load_manifest()
    extras = (
        [item.strip() for item in args.extras.split(",") if item.strip()]
        if args.extras
        else manifest["install_contract"].get("lightweight_extra_smoke", [])
    )
    if not extras:
        raise SystemExit("No extras selected for smoke")

    failures: list[str] = []
    for extra in extras:
        ok, message = smoke_extra(extra, timeout=args.timeout)
        print(message)
        if not ok:
            failures.append(message)

    if failures:
        print("Optional extra smoke FAILED:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure.splitlines()[0]}", file=sys.stderr)
        return 1
    print("Optional extra smoke OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
