#!/usr/bin/env python3
# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Validate that public imports are quiet and do not load optional engines."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

BANNED_MODULE_PREFIXES = (
    "numpy",
    "cv2",
    "rapidocr_onnxruntime",
    "onnxruntime",
    "fitz",
    "pdfplumber",
    "fastapi",
    "openai",
    "google.generativeai",
)

CHECKS = {
    "import_docmirror": "import docmirror; print(docmirror.__version__)",
    "import_cli": "import docmirror.cli.main; print('cli-ok')",
}


def _expected_version() -> str:
    init_path = REPO_ROOT / "docmirror" / "__init__.py"
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', init_path.read_text(encoding="utf-8"), re.MULTILINE)
    if not match:
        raise RuntimeError("docmirror/__init__.py does not define literal __version__")
    return match.group(1)


def _run_check(name: str, code: str) -> list[str]:
    probe = f"import json, sys\n{code}\nprint('__DOCMIRROR_MODULES__=' + json.dumps(sorted(sys.modules)))\n"
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    errors: list[str] = []
    if result.returncode != 0:
        errors.append(f"{name}: command failed: {result.stderr.strip() or result.stdout.strip()}")
        return errors

    stdout_lines = result.stdout.splitlines()
    marker_lines = [line for line in stdout_lines if line.startswith("__DOCMIRROR_MODULES__=")]
    visible_lines = [line for line in stdout_lines if not line.startswith("__DOCMIRROR_MODULES__=")]
    if result.stderr.strip():
        errors.append(f"{name}: stderr is not quiet: {result.stderr.strip()}")
    if name == "import_docmirror" and visible_lines != [_expected_version()]:
        errors.append(f"{name}: unexpected stdout: {visible_lines!r}")
    if name == "import_cli" and visible_lines != ["cli-ok"]:
        errors.append(f"{name}: unexpected stdout: {visible_lines!r}")
    if not marker_lines:
        errors.append(f"{name}: module probe marker missing")
        return errors
    modules = json.loads(marker_lines[-1].split("=", 1)[1])
    banned_loaded = [
        module
        for module in modules
        if any(module == prefix or module.startswith(prefix + ".") for prefix in BANNED_MODULE_PREFIXES)
    ]
    if banned_loaded:
        errors.append(f"{name}: optional/heavy modules loaded during public import: {banned_loaded[:20]}")
    return errors


def main() -> int:
    errors: list[str] = []
    for name, code in CHECKS.items():
        errors.extend(_run_check(name, code))
    if errors:
        print("Import purity validation FAILED:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("Import purity validation OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
