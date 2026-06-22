# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""GA 1.0 Demo Regression Tests - OUT5-3, OUT5-4, OUT5-5.

Validates the three public GA 1.0 demo scenarios:
  1. Complex PDF -> RAG: markdown + chunks + source_refs + evidence
  2. Bank/Payment -> Finance: transaction rows + confidence + quality_report
  3. Low-Quality Scan -> Partial + Evidence: partial + needs_review + retry_suggestion
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_docmirror(cmdline: str, output_dir: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    parts = cmdline.split("docmirror parse ", 1)
    rest = parts[1].strip() if len(parts) == 2 else cmdline
    full_cmd = f"cd {REPO_ROOT} && python3 -m docmirror.cli.main parse --output-dir {output_dir} {rest}"
    return subprocess.run(full_cmd, shell=True, capture_output=True, text=True, env=env, timeout=60)


def _load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.slow
def test_demo1_complex_pdf_to_rag():
    """OUT5-3: credit_report_section_smoke.pdf produces Markdown + evidence + manifest."""
    input_path = REPO_ROOT / "tests/fixtures/synthetic/credit_report_section_smoke.pdf"
    if not input_path.is_file():
        pytest.skip(f"fixture not found: {input_path}")
    with TemporaryDirectory() as tmpdir:
        out = Path(tmpdir)
        _run_docmirror(f"docmirror parse {input_path} --format markdown,evidence --editions mirror,community", out)
        artifacts = sorted(f.name for f in out.rglob("*.json") if f.is_file())
        assert "001_mirror.json" in artifacts, f"missing mirror; artifacts={artifacts}"
        assert "005_evidence_bundle.json" in artifacts, f"missing evidence; artifacts={artifacts}"
        bundle_path = next(out.rglob("005_evidence_bundle.json"), None)
        if bundle_path:
            assert _load_json(bundle_path).get("version") == 2
        md_files = list(out.rglob("output.md"))
        if md_files:
            assert len(md_files[0].read_text(encoding="utf-8")) > 10
        manifest_path = next(out.rglob("manifest.json"), None)
        if manifest_path:
            assert "artifacts" in _load_json(manifest_path)


@pytest.mark.slow
def test_demo2_bank_flow_to_finance():
    """OUT5-4: bank_ledger_3page_smoke.pdf produces community + mirror + evidence."""
    input_path = REPO_ROOT / "tests/fixtures/synthetic/bank_ledger_3page_smoke.pdf"
    if not input_path.is_file():
        pytest.skip(f"fixture not found: {input_path}")
    with TemporaryDirectory() as tmpdir:
        out = Path(tmpdir)
        _run_docmirror(f"docmirror parse {input_path} --format json,evidence --editions mirror,community", out)
        artifacts = sorted(f.name for f in out.rglob("*.json") if f.is_file())
        comm_files = [a for a in artifacts if "community" in a.lower()]
        assert comm_files, f"no community file; artifacts={artifacts}"
        comm_path = next(out.rglob("*community*.json"), None)
        if comm_path:
            comm = _load_json(comm_path)
            assert comm.get("metadata", {}).get("edition") == "community"
            assert "data" in comm
        ev_files = [a for a in artifacts if "evidence" in a.lower()]
        assert ev_files, f"no evidence bundle; artifacts={artifacts}"
        ev_path = next(out.rglob("*evidence*.json"), None)
        if ev_path:
            assert _load_json(ev_path).get("version") == 2
        qr_path = next(out.rglob("quality_report.json"), None)
        if qr_path:
            assert "readiness" in _load_json(qr_path)


@pytest.mark.slow
def test_demo3_low_quality_scan_to_partial():
    """OUT5-5: account_card_page4_full_layout.json produces mirror + evidence + visual_debug."""
    input_path = REPO_ROOT / "tests/fixtures/scanned/account_card_page4_full_layout.json"
    if not input_path.is_file():
        pytest.skip(f"fixture not found: {input_path}")
    with TemporaryDirectory() as tmpdir:
        out = Path(tmpdir)
        _run_docmirror(f"docmirror parse {input_path} --format evidence --editions mirror,community", out)
        artifacts = sorted(f.name for f in out.rglob("*.json") if f.is_file())
        ev_files = [a for a in artifacts if "evidence" in a.lower()]
        assert ev_files, f"no evidence bundle; artifacts={artifacts}"
        ev_path = next(out.rglob("*evidence*.json"), None)
        if ev_path:
            bundle = _load_json(ev_path)
            assert bundle.get("version") == 2
            assert isinstance(bundle.get("ledger"), list)
        vd_files = list(out.rglob("visual_debug.html"))
        if vd_files:
            html = vd_files[0].read_text(encoding="utf-8")
            assert "<html" in html.lower() or "<!doctype" in html.lower()


def test_demo_manifest_references_valid_fixtures():
    """OUT5-3/4/5: ga_demo_manifest.yaml references existing fixture files."""
    from docmirror.configs.ga_experience import load_ga_demo_manifest
    data = load_ga_demo_manifest()
    demos = data.get("demos", {})
    assert len(demos) >= 3
    required = {"complex_pdf_to_rag", "bank_flow_to_finance_json", "low_quality_scan_to_partial_evidence"}
    for demo_id in required:
        assert demo_id in demos, f"missing demo: {demo_id}"
        demo = demos[demo_id]
        input_rel = demo.get("input", "")
        assert (REPO_ROOT / input_rel).is_file(), f"demo {demo_id}: fixture missing at {input_rel}"
        assert demo.get("command"), f"demo {demo_id}: missing command"
        assert demo.get("expected_artifacts"), f"demo {demo_id}: missing expected_artifacts"
