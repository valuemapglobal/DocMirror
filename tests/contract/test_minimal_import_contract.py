# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Minimal public import contract."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_import_docmirror_is_quiet_and_light():
    result = subprocess.run(
        [sys.executable, "scripts/validate/validate_import_purity.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_deep_optional_modules_do_not_import_numpy_at_module_import():
    script = """
import importlib
import sys
for name in (
    'docmirror.input.extraction.extractor',
    'docmirror.structure.segment.negative_space',
):
    importlib.import_module(name)
assert 'numpy' not in sys.modules, sorted(k for k in sys.modules if k.startswith('numpy'))[:5]
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
