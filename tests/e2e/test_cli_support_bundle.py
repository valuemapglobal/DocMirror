# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""W7-05: CLI support bundle E2E tests.

GA 1.0 design SS9 Wave 7: Validates that handle_debug_support_bundle
generates a redaction-safe support bundle zip from a task directory.
"""

import json as _json
import tempfile
import os
import zipfile
from pathlib import Path

import pytest

from docmirror.cli.explainability_commands import handle_debug_support_bundle


def _make_task_dir_with_artifacts(base: Path, label: str) -> Path:
    task_dir = base / label
    task_dir.mkdir(parents=True, exist_ok=True)

    _write_json(task_dir / "manifest.json", {
        "version": 1,
        "document_id": "doc_support",
        "task_id": f"task_{label}",
        "output_profile": "quickstart",
        "artifacts": {},
    })
    _write_json(task_dir / "quality_report.json", {
        "version": 1, "status": "success",
        "text_fidelity": "pass", "layout_fidelity": "pass",
    })
    _write_json(task_dir / "quality_decision.json", {
        "version": 2, "decision": "auto_ingest",
        "decision_reason": "all_passed",
    })
    _write_json(task_dir / "visual_evidence_graph.json", {
        "version": 1, "nodes": {}, "edges": [], "pages": [],
    })
    _write_json(task_dir / "overlay_manifest.json", {
        "version": 1, "layers": [], "overlays": [],
    })
    _write_json(task_dir / "source_span_ledger.json", {
        "version": 1, "field_spans": [], "unresolved_fields": [],
    })
    _write_json(task_dir / "outcome_ledger.json", {
        "version": 1, "events": [],
    })
    _write_json(task_dir / "schema_validation.json", {
        "version": 1, "valid": True, "errors": [],
    })
    return task_dir


def _write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _list_zip_contents(zip_path: Path) -> list[str]:
    with zipfile.ZipFile(str(zip_path), "r") as zf:
        return sorted(zf.namelist())


def test_cli_support_bundle_minimal_profile():
    """minimal profile must create a zip with only manifest, quality, decision."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        task_dir = _make_task_dir_with_artifacts(base, "task_001")

        output = base / "support_minimal.zip"
        result = handle_debug_support_bundle(
            str(task_dir), profile="minimal", output=str(output),
        )

        assert result.exists()
        contents = _list_zip_contents(result)

        # Minimal profile: manifest + quality reports only
        assert "manifest.json" in contents
        assert "quality_report.json" in contents or "quality_decision.json" in contents
        assert "support_bundle_manifest.json" in contents

        # Non-minimal files should NOT be in minimal profile
        assert "visual_evidence_graph.json" not in contents
        assert "source_span_ledger.json" not in contents


def test_cli_support_bundle_redacted_profile():
    """redacted profile must include overlay/graph/source but not raw content."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        task_dir = _make_task_dir_with_artifacts(base, "task_001")

        output = base / "support_redacted.zip"
        result = handle_debug_support_bundle(
            str(task_dir), profile="redacted", output=str(output),
        )

        assert result.exists()
        contents = _list_zip_contents(result)

        assert "manifest.json" in contents
        assert "visual_evidence_graph.json" in contents
        assert "overlay_manifest.json" in contents
        assert "source_span_ledger.json" in contents
        assert "outcome_ledger.json" in contents
        assert "support_bundle_manifest.json" in contents


def test_cli_support_bundle_forensic_profile():
    """forensic_internal profile must include mirror and markdown."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        task_dir = _make_task_dir_with_artifacts(base, "task_001")
        _write_json(task_dir / "001_mirror.json", {"status": "success"})
        task_dir.joinpath("output.md").write_text("# Test Document", encoding="utf-8")

        output = base / "support_forensic.zip"
        result = handle_debug_support_bundle(
            str(task_dir), profile="forensic_internal", output=str(output),
        )

        assert result.exists()
        contents = _list_zip_contents(result)

        assert "001_mirror.json" in contents
        assert "output.md" in contents
        assert "support_bundle_manifest.json" in contents


def test_cli_support_bundle_manifest_has_profiles():
    """Support bundle manifest must declare profile and redaction_safe."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        task_dir = _make_task_dir_with_artifacts(base, "task_001")

        output = base / "support_profiles.zip"
        result = handle_debug_support_bundle(
            str(task_dir), profile="redacted", output=str(output),
        )

        with zipfile.ZipFile(str(result), "r") as zf:
            manifest_raw = zf.read("support_bundle_manifest.json")
            manifest = _json.loads(manifest_raw)

        assert manifest["version"] == 1
        assert manifest["profile"] == "redacted"
        assert manifest["redaction_safe"] is True
        assert "includes" in manifest
        assert "excludes" in manifest
        assert isinstance(manifest["includes"], list)
        assert isinstance(manifest["excludes"], list)

        # Forensic profile must have redaction_safe=false
        result2 = handle_debug_support_bundle(
            str(task_dir), profile="forensic_internal",
            output=str(base / "support_forensic2.zip"),
        )
        with zipfile.ZipFile(str(result2), "r") as zf:
            manifest2 = _json.loads(zf.read("support_bundle_manifest.json"))
        assert manifest2["profile"] == "forensic_internal"
        assert manifest2["redaction_safe"] is False


def test_cli_support_bundle_missing_manifest():
    """handle_debug_support_bundle must raise FileNotFoundError if manifest.json missing."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        task_dir = base / "no_manifest"
        task_dir.mkdir()

        with pytest.raises(FileNotFoundError, match="manifest.json"):
            handle_debug_support_bundle(str(task_dir), profile="minimal")


def test_cli_support_bundle_default_profile():
    """Default profile (redacted) must create a valid zip."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        task_dir = _make_task_dir_with_artifacts(base, "task_default")

        output = base / "support_default.zip"
        result = handle_debug_support_bundle(
            str(task_dir), output=str(output),
        )

        assert result.exists()
        contents = _list_zip_contents(result)
        # Default profile is "redacted"
        assert "visual_evidence_graph.json" in contents


def test_cli_support_bundle_no_output_arg():
    """When output is not given, the bundle must be written to task_dir/support_bundle.zip."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        task_dir = _make_task_dir_with_artifacts(base, "task_nooutput")

        result = handle_debug_support_bundle(str(task_dir), profile="minimal")

        assert result.exists()
        assert result.parent == task_dir
        assert result.name == "support_bundle.zip"
