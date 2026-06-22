# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""W7-04: CLI diff two runs E2E tests.

GA 1.0 design SS9 Wave 7: Validates that handle_diff correctly compares
two task output directories and produces a diff report with changed nodes,
severity ratings, and visual diff overlay data.
"""

import json as _json
import tempfile
import os
from pathlib import Path

import pytest

from docmirror.cli.explainability_commands import handle_diff


def _write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _make_task_dir(base: Path, label: str, fields: dict, extra_nodes=None) -> Path:
    task_dir = base / label
    task_dir.mkdir(parents=True, exist_ok=True)

    graph = {
        "version": 1,
        "document_id": "doc_diff",
        "task_id": f"task_{label}",
        "coordinate_system": "pdf_points_top_left",
        "pages": [
            {"page": 1, "width": 595, "height": 842,
             "image_ref": "page_images/page_001.png", "nodes": []}
        ],
        "nodes": {
            "page:p1": {"id": "page:p1", "kind": "page", "label": "Page 1",
                         "page": 1, "bbox": [0, 0, 595, 842],
                         "confidence": 1.0},
            "block:p1:b0": {"id": "block:p1:b0", "kind": "block", "label": "Title",
                             "page": 1, "bbox": [20, 40, 520, 90],
                             "confidence": 0.98},
            "table:p1:t0": {"id": "table:p1:t0", "kind": "table", "label": "Table 0",
                             "page": 1, "bbox": [50, 150, 545, 600],
                             "confidence": 0.95},
            **fields,
        },
        "edges": [
            {"id": "e1", "type": "contains", "from": "page:p1", "to": "block:p1:b0",
             "confidence": 1.0, "provenance": {}},
            {"id": "e2", "type": "contains", "from": "page:p1", "to": "table:p1:t0",
             "confidence": 1.0, "provenance": {}},
        ],
        "layers": [], "quality": {}, "outcomes": {}, "redaction": {},
    }
    if extra_nodes:
        graph["nodes"].update(extra_nodes)

    _write_json(task_dir / "visual_evidence_graph.json", graph)
    _write_json(task_dir / "quality_decision.json", {
        "version": 2,
        "decision": "auto_ingest",
        "decision_reason": "all_checks_passed",
        "confidence_policy": "ga_default_v1",
        "summary": {"text_fidelity": "pass", "layout_fidelity": "pass",
                     "business_fidelity": "pass", "audit_fidelity": "pass"},
        "blocking_issues": [],
        "needs_review": [],
        "metrics": {},
    })
    _write_json(task_dir / "manifest.json", {
        "document_id": "doc_diff", "task_id": f"task_{label}",
        "output_profile": "quickstart",
    })
    return task_dir


def _base_fields():
    return {
        "field:inv.total": {
            "id": "field:inv.total", "kind": "field", "label": "total",
            "page": 1, "bbox": [400, 700, 500, 720],
            "confidence": 0.95, "value_preview": "100.00",
            "field_path": "inv.total",
            "source_refs": ["cell:p1:t0:r0:c0"],
            "review": "auto_accepted",
        },
        "field:inv.vendor": {
            "id": "field:inv.vendor", "kind": "field", "label": "vendor",
            "page": 1, "bbox": [100, 100, 300, 120],
            "confidence": 0.93, "value_preview": "ACME Corp",
            "field_path": "inv.vendor",
            "source_refs": ["text:p1:span2"],
            "review": "auto_accepted",
        },
    }


def test_cli_diff_identical_runs():
    """Two identical task dirs must produce pass with no changes."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        fields = _base_fields()
        run_a = _make_task_dir(base, "run_a", fields)
        run_b = _make_task_dir(base, "run_b", fields)

        result = handle_diff(str(run_a), str(run_b))

        assert result["status"] == "pass"
        assert result["summary"]["total_changes"] == 0
        assert len(result["changes"]) == 0


def test_cli_diff_field_value_changed():
    """Changed field value must be detected and reported."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        fields_a = _base_fields()
        fields_b = _base_fields()
        fields_b["field:inv.total"]["value_preview"] = "200.00"

        run_a = _make_task_dir(base, "run_a", fields_a)
        run_b = _make_task_dir(base, "run_b", fields_b)

        result = handle_diff(str(run_a), str(run_b))

        assert result["status"] in ("warning", "fail")
        field_changes = [c for c in result["changes"] if c["kind"] == "field_value_changed"]
        assert len(field_changes) == 1
        assert field_changes[0]["node_id"] == "field:inv.total"


def test_cli_diff_node_added_removed():
    """Node addition and removal must be detected."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        fields_a = _base_fields()
        fields_b = dict(fields_a)
        del fields_b["field:inv.vendor"]
        # Add new node not in base
        fields_b["field:inv.new"] = {
            "id": "field:inv.new", "kind": "field", "label": "new_field",
            "page": 1, "bbox": [10, 20, 30, 40],
            "confidence": 0.9, "value_preview": "42",
            "field_path": "inv.new",
            "source_refs": [],
            "review": "auto_accepted",
        }

        run_a = _make_task_dir(base, "run_a", fields_a)
        run_b = _make_task_dir(base, "run_b", fields_b)

        result = handle_diff(str(run_a), str(run_b))

        added = [c for c in result["changes"] if c["kind"] == "node_added"]
        removed = [c for c in result["changes"] if c["kind"] == "node_removed"]
        assert len(added) >= 1, f"No node_added changes, got: {[c['kind'] for c in result['changes']]}"
        assert len(removed) >= 1


def test_cli_diff_quality_decision_change():
    """Quality decision change must be reported."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        fields = _base_fields()
        run_a = _make_task_dir(base, "run_a", fields)
        run_b = _make_task_dir(base, "run_b", fields)

        # Override quality decision in run_b
        _write_json(run_b / "quality_decision.json", {
            "version": 2,
            "decision": "needs_review",
            "decision_reason": "low_coverage",
            "confidence_policy": "ga_default_v1",
            "summary": {},
            "blocking_issues": [],
            "needs_review": [{"scope": "field", "field_path": "inv.total",
                              "node_id": "field:inv.total",
                              "reason": "low_confidence"}],
            "metrics": {},
        })

        result = handle_diff(str(run_a), str(run_b))
        qd_changes = [c for c in result["changes"] if c["kind"] == "quality_decision_changed"]
        assert len(qd_changes) == 1


def test_cli_diff_output_json_file():
    """handle_diff must write JSON output when an output path is given."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        fields = _base_fields()
        run_a = _make_task_dir(base, "run_a", fields)
        run_b = _make_task_dir(base, "run_b", fields)

        output_path = base / "diff_output.json"
        result = handle_diff(str(run_a), str(run_b), output=str(output_path), format="json")

        assert output_path.is_file()
        written = _json.loads(output_path.read_text(encoding="utf-8"))
        assert written["status"] == "pass"
        assert result["status"] == "pass"


def test_cli_diff_output_html_file():
    """handle_diff must write HTML output when format=html is given."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        fields = _base_fields()
        run_a = _make_task_dir(base, "run_a", fields)
        run_b = _make_task_dir(base, "run_b", fields)

        output_path = base / "diff_output.html"
        result = handle_diff(str(run_a), str(run_b), output=str(output_path), format="html")

        assert output_path.is_file()
        html = output_path.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in html
        assert "DocMirror Diff Report" in html


def test_cli_diff_missing_visual_graph():
    """handle_diff must handle directories without visual_evidence_graph.json gracefully."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        run_a = base / "run_a"
        run_b = base / "run_b"
        run_a.mkdir(parents=True)
        run_b.mkdir(parents=True)

        result = handle_diff(str(run_a), str(run_b))
        assert result["status"] == "pass"
        assert result["summary"]["total_changes"] == 0
