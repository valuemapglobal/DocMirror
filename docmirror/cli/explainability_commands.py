# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""CLI command handlers for explainability and visualization (W4-04, W5-04, W6-04).

Provides handler functions for ``docmirror diff``, ``docmirror debug visual``,
and ``docmirror debug support-bundle`` commands. These functions are designed
to be wired into Click or argparse command groups.
"""

from __future__ import annotations

import json as _json
from pathlib import Path
from typing import Any


def handle_diff(
    base_dir: str | Path,
    candidate_dir: str | Path,
    *,
    output: str | Path | None = None,
    format: str = "json",
) -> dict[str, Any]:
    """Compare two task output directories and produce a DiffReport.

    Args:
        base_dir: Path to the base run's output directory.
        candidate_dir: Path to the candidate run's output directory.
        output: Optional output file path for the diff report.
        format: Output format: "json" or "html".

    Returns:
        DiffReport dict.
    """
    base_dir = Path(base_dir)
    candidate_dir = Path(candidate_dir)

    from docmirror.evidence.diff_canonicalizer import (
        canonicalize_visual_graph,
        canonicalize_quality_decision,
    )
    from docmirror.evidence.diff_engine import diff_graphs

    def load_graph(run_dir: Path) -> dict[str, Any]:
        veg_path = run_dir / "visual_evidence_graph.json"
        if veg_path.is_file():
            data = _json.loads(veg_path.read_text(encoding="utf-8"))
            return canonicalize_visual_graph(data)
        return canonicalize_visual_graph(None)

    def load_quality(run_dir: Path) -> dict[str, Any]:
        qd_path = run_dir / "quality_decision.json"
        if qd_path.is_file():
            data = _json.loads(qd_path.read_text(encoding="utf-8"))
            return canonicalize_quality_decision(data)
        return canonicalize_quality_decision(None)

    base_graph = load_graph(base_dir)
    cand_graph = load_graph(candidate_dir)
    base_graph["quality_decision"] = load_quality(base_dir)
    cand_graph["quality_decision"] = load_quality(candidate_dir)

    report = diff_graphs(
        base_graph, cand_graph,
        base_run=str(base_dir.name),
        candidate_run=str(candidate_dir.name),
    )
    result = report.to_dict()

    if output:
        output = Path(output)
        if format == "html":
            html = _diff_report_to_html(result, str(base_dir.name), str(candidate_dir.name))
            Path(output).write_text(html, encoding="utf-8")
        else:
            Path(output).write_text(
                _json.dumps(result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    return result


def handle_debug_visual(
    task_dir: str | Path,
    *,
    pdf_path: str | None = None,
) -> Path:
    """Generate visual_debug.html and associated artifacts from a task directory.

    Reads the manifest.json in task_dir, rebuilds the visual graph and overlay
    manifest, and writes visual_debug.html.

    Args:
        task_dir: Path to the task output directory.
        pdf_path: Optional path to the original PDF for page image rendering.

    Returns:
        Path to the generated visual_debug.html.
    """
    task_dir = Path(task_dir)
    manifest_path = task_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"manifest.json not found in {task_dir}")

    manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))

    from docmirror.evidence.visual_graph import build_visual_evidence_graph
    from docmirror.evidence.overlay_manifest import build_overlay_manifest
    from docmirror.evidence.source_span import build_source_span_ledger
    from docmirror.evidence.quality_decision import build_quality_decision
    from docmirror.server.artifact_pack import _build_visual_debug_html_v3

    # Rebuild from mirror if available
    mirror_path = task_dir / "001_mirror.json"
    result = None
    if mirror_path.is_file():
        result = _json.loads(mirror_path.read_text(encoding="utf-8"))

    editions: dict[str, Any] = {}
    for edition_name in ("002_community", "003_enterprise", "004_finance"):
        ep = task_dir / f"{edition_name}.json"
        if ep.is_file():
            editions[edition_name] = _json.loads(ep.read_text(encoding="utf-8"))

    graph = build_visual_evidence_graph(result, editions=editions,
                                         document_id=manifest.get("document_id", ""),
                                         task_id=manifest.get("task_id", ""))
    overlay = build_overlay_manifest(graph)
    ledger = build_source_span_ledger(result, editions=editions,
                                       document_id=manifest.get("document_id", ""),
                                       task_id=manifest.get("task_id", ""))
    quality_dec = build_quality_decision(
        visual_graph=graph,
        source_span_ledger=ledger,
        editions=editions,
        document_id=manifest.get("document_id", ""),
        task_id=manifest.get("task_id", ""),
    )

    from docmirror.server.artifact_pack import ensure_quickstart_artifact_pack
    ensure_quickstart_artifact_pack(
        task_dir, manifest,
        result=result,
        visual_graph=graph,
        overlay_manifest=overlay,
        source_span_ledger=ledger,
        quality_decision=quality_dec,
        pdf_path=pdf_path,
    )

    visual_path = task_dir / "visual_debug.html"
    return visual_path


def handle_debug_support_bundle(
    task_dir: str | Path,
    *,
    profile: str = "redacted",
    output: str | Path | None = None,
) -> Path:
    """Generate a support bundle from a task directory.

    Args:
        task_dir: Path to the task output directory.
        profile: Redaction profile: minimal, redacted, evidence_only, forensic_internal.
        output: Optional output path for the support bundle zip.

    Returns:
        Path to the generated support bundle zip.
    """
    task_dir = Path(task_dir)
    manifest_path = task_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"manifest.json not found in {task_dir}")

    import zipfile
    from datetime import datetime, timezone

    manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))

    include_sensitive = (profile == "forensic_internal")
    output = Path(output) if output else task_dir / "support_bundle.zip"

    with zipfile.ZipFile(str(output), "w", zipfile.ZIP_DEFLATED) as zf:
        # manifest
        zf.writestr("support_bundle_manifest.json", _json.dumps({
            "version": 1,
            "profile": profile,
            "redaction_safe": profile != "forensic_internal",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "task_id": manifest.get("task_id", ""),
            "document_id": manifest.get("document_id", ""),
            "includes": _build_includes_list(profile),
            "excludes": _build_excludes_list(profile),
        }, ensure_ascii=False, indent=2))

        # Always include: manifest.json, quality_report.json
        for name in ("manifest.json", "quality_report.json", "quality_decision.json"):
            p = task_dir / name
            if p.is_file():
                zf.write(str(p), p.name)

        # Include based on profile
        if profile in ("redacted", "evidence_only", "forensic_internal"):
            _add_if_exists(zf, task_dir, "visual_evidence_graph.json")
            _add_if_exists(zf, task_dir, "overlay_manifest.json")
            _add_if_exists(zf, task_dir, "source_span_ledger.json")
            _add_if_exists(zf, task_dir, "outcome_ledger.json")
            _add_if_exists(zf, task_dir, "schema_validation.json")

        if profile == "forensic_internal":
            _add_if_exists(zf, task_dir, "001_mirror.json")
            _add_if_exists(zf, task_dir, "output.md")

    return Path(output)


def _add_if_exists(zf: zipfile.ZipFile, task_dir: Path, filename: str) -> None:
    p = task_dir / filename
    if p.is_file():
        zf.write(str(p), p.name)


def _build_includes_list(profile: str) -> list[str]:
    base = ["manifest.json", "support_bundle_manifest.json", "quality_report.json"]
    if profile in ("redacted", "evidence_only", "forensic_internal"):
        base.extend([
            "visual_evidence_graph.json", "overlay_manifest.json",
            "source_span_ledger.json", "outcome_ledger.json",
            "schema_validation.json",
        ])
    if profile == "forensic_internal":
        base.extend(["001_mirror.json", "output.md"])
    return base


def _build_excludes_list(profile: str) -> list[str]:
    if profile == "forensic_internal":
        return ["license_key", "api_key"]
    return ["raw_text", "raw_page_images", "license_key", "api_key"]


def _diff_report_to_html(report: dict[str, Any], base_name: str, cand_name: str) -> str:
    """Render a diff report as a simple HTML page."""
    changes_html = ""
    for c in report.get("changes", []):
        sev = c.get("severity", "low")
        sev_color = "#cf222e" if sev == "high" else "#d29922" if sev == "medium" else "#54aeff"
        changes_html += f"""<tr>
  <td><span style="color:{sev_color};font-weight:600">{sev}</span></td>
  <td>{c.get("kind", "")}</td>
  <td>{c.get("node_id", "")}</td>
  <td>{c.get("before", "")}</td>
  <td>{c.get("after", "")}</td>
  <td>{c.get("message", "")}</td>
</tr>"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>DocMirror Diff Report</title>
<style>
body {{ font-family: -apple-system, sans-serif; max-width: 1200px; margin: 20px auto; padding: 0 20px; background: #0d1117; color: #c9d1d9; }}
h1 {{ color: #58a6ff; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
th {{ background: #161b22; padding: 8px 12px; text-align: left; border-bottom: 1px solid #30363d; }}
td {{ padding: 6px 12px; border-bottom: 1px solid #21262d; font-size: 13px; }}
.summary {{ display: flex; gap: 16px; margin: 16px 0; }}
.summary-item {{ background: #161b22; padding: 12px 16px; border-radius: 6px; border: 1px solid #30363d; }}
.summary-value {{ font-size: 24px; font-weight: 700; }}
.status-pass {{ color: #3fb950; }}
.status-warning {{ color: #d29922; }}
.status-fail {{ color: #f85149; }}
</style></head><body>
<h1>DocMirror Diff Report</h1>
<p>{base_name} vs {cand_name}</p>
<div class="summary">
  <div class="summary-item"><div>Status</div><div class="summary-value status-{report.get("status","")}">{report.get("status","")}</div></div>
  <div class="summary-item"><div>Total Changes</div><div class="summary-value">{report.get("summary",{}).get("total_changes",0)}</div></div>
</div>
<table>
<tr><th>Severity</th><th>Kind</th><th>Node</th><th>Before</th><th>After</th><th>Message</th></tr>
{changes_html}
</table>
</body></html>"""


__all__ = [
    "handle_diff",
    "handle_debug_visual",
    "handle_debug_support_bundle",
]
