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
    script = ROOT / "scripts" / "audit_core_imports.py"
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


def test_segment_zones_has_no_lazy_hub() -> None:
    report = _audit_report()
    assert report.get("lazy_hub_present") is False, "segment/zones.py must not use __getattr__ lazy re-exports"


def test_cps_layout_validator_passes() -> None:
    script = ROOT / "scripts" / "validate_core_cps_layout.py"
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, result.stdout + result.stderr


def test_import_linter_contract() -> None:
    if os.environ.get("CI"):
        import importlinter  # noqa: F401
    else:
        pytest.importorskip("importlinter")

    result = subprocess.run([sys.executable, "-m", "lint_imports"], capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, result.stdout + result.stderr


def test_page_pipeline_orchestrates_cps_stages() -> None:
    from docmirror.core.pipeline.context import PageExtractionContext
    from docmirror.core.pipeline.page_pipeline import PagePipeline

    host = MagicMock()
    ctx = MagicMock(spec=PageExtractionContext)
    ctx.page_plum = MagicMock()
    ctx.page_idx = 0
    ctx.fitz_page = MagicMock()
    ctx.fitz_page.rect.width = 612.0
    ctx.fitz_page.rect.height = 792.0
    ctx.extraction_profile = None
    ctx.global_table_template = None
    ctx.content_type = "table_dominant"
    expected = (MagicMock(), ["ocr"], "pdfplumber_default", 0.9)

    with (
        patch("docmirror.core.pipeline.page_pipeline.run_prepare") as prep,
        patch("docmirror.core.pipeline.page_pipeline.run_segment") as seg,
        patch("docmirror.core.pipeline.page_pipeline.run_assemble_zones") as asm,
        patch("docmirror.core.pipeline.page_pipeline.run_finalize") as fin,
        patch("docmirror.core.pipeline.page_pipeline.PageExtractor") as pe_cls,
    ):
        prep.return_value = (ctx.page_plum, True, None)
        seg.return_value = ([], False, 1.0)
        asm.return_value = ([], [], False, "pdfplumber_default", 0.9, ["ocr"], [], 0.0, 0.0)
        fin.return_value = expected
        pe_cls.return_value._extract_page_styles.return_value = {}
        result = PagePipeline(host).run(ctx)

    prep.assert_called_once()
    seg.assert_called_once()
    asm.assert_called_once()
    fin.assert_called_once()
    assert result == expected
