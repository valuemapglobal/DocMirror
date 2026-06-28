# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""CCP import contract tests (CPA design 12 §4.3)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.tier_contract]

ROOT = Path(__file__).resolve().parents[2]


def _audit_report() -> dict:
    script = ROOT / "scripts" / "validate" / "audit_core_imports.py"
    out = ROOT / "reports" / "ccp_test_audit.json"
    subprocess.run(
        [sys.executable, str(script), "--json", str(out)],
        check=True,
        cwd=ROOT,
    )
    return json.loads(out.read_text(encoding="utf-8"))


def test_plugins_forbidden_core_internals() -> None:
    report = _audit_report()
    violations = report.get("plugin_forbidden_imports", [])
    assert violations == [], f"CCP violations: {violations}"


def test_core_does_not_import_plugin_or_server_layers() -> None:
    report = _audit_report()
    violations = [
        item
        for item in report.get("efmp_boundary_violations", [])
        if item.get("rule") in {"core_must_not_depend_on_plugins", "core_must_not_depend_on_server"}
    ]
    assert violations == [], f"Core EFMP boundary violations: {violations}"


def test_segment_zones_has_no_lazy_hub() -> None:
    report = _audit_report()
    assert report.get("lazy_hub_present") is False, "segment/zones.py must not use __getattr__ lazy re-exports"


def test_cps_layout_validator_passes() -> None:
    script = ROOT / "scripts" / "validate" / "validate_core_cps_layout.py"
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, result.stdout + result.stderr


def test_import_linter_contract() -> None:
    import shutil

    if os.environ.get("CI"):
        import importlinter  # noqa: F401
    else:
        pytest.importorskip("importlinter")

    lint_imports = shutil.which("lint-imports")
    assert lint_imports, "lint-imports CLI not found (pip install import-linter)"
    subprocess.run(
        [sys.executable, "scripts/validate/generate_import_linter.py", "--check"],
        check=True,
        cwd=ROOT,
    )
    result = subprocess.run([lint_imports, "--config", ".importlinter"], capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, result.stdout + result.stderr


def test_legacy_input_pipeline_removed() -> None:
    assert not (ROOT / "docmirror" / "input" / "pipeline" / "legacy").exists()
