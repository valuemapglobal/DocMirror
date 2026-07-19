# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Quickstart artifact pack helpers -- GA 1.0 v3.

Generates output.md, quality_report.json, visual_debug.html, evidence/,
visual_evidence_graph.json, overlay_manifest.json, source_span_ledger.json,
quality_decision.json, artifact_roles, and schema_versions.

The v3 visual_debug.html is a self-contained static visualizer with page
images, SVG overlays, layer toggles, and an inspector panel. All
explainability artifacts share the Visual Evidence Graph as their single
source of truth (XVC SS4.3).
"""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

from docmirror import __version__
from docmirror.configs.output_profile import OutputProfile, default_profile
from docmirror.runtime.serialization import dumps_json

_TPL_DIR = Path(__file__).resolve().parent.parent / "evidence" / "templates"


def _read_template(filename: str) -> str:
    """Read a template file from the evidence/templates directory."""
    path = _TPL_DIR / filename
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return ""


def _build_schema_versions() -> dict[str, str]:
    return {
        "mirror": "1.x",
        "community": "2.x",
        "enterprise": "2.x",
        "finance": "3.x",
        "evidence_bundle": "2.x",
        "visual_evidence_graph": "1.x",
        "overlay_manifest": "1.x",
        "source_span_ledger": "1.x",
        "quality_decision": "2.x",
        "diff_report": "1.x",
        "support_bundle": "2.x",
        "manifest": "2.x",
    }


def _build_artifact_roles(manifest: dict[str, Any]) -> dict[str, str | None]:
    artifacts = manifest.get("artifacts") or {}
    return {
        "mirror": artifacts.get("mirror") or artifacts.get("json"),
        "community": artifacts.get("community"),
        "enterprise": artifacts.get("enterprise"),
        "finance": artifacts.get("finance"),
        "markdown": artifacts.get("markdown") or artifacts.get("quickstart_markdown"),
        "evidence_bundle": artifacts.get("evidence"),
        "quality_report": artifacts.get("quality_report"),
        "quality_decision": artifacts.get("quality_decision"),
        "visual_debug": artifacts.get("visual_debug"),
        "visual_evidence_graph": artifacts.get("visual_evidence_graph"),
        "overlay_manifest": artifacts.get("overlay_manifest"),
        "source_span_ledger": artifacts.get("source_span_ledger"),
        "layout_overlay": artifacts.get("layout_overlay"),
    }


def ensure_quickstart_artifact_pack(
    task_dir: Path,
    manifest: dict[str, Any],
    *,
    result: Any | None = None,
    profile: OutputProfile | None = None,
    visual_graph: Any | None = None,
    overlay_manifest: dict[str, Any] | None = None,
    source_span_ledger: Any | None = None,
    quality_decision: Any | None = None,
    pdf_path: str | None = None,
) -> dict[str, Any]:
    """Write user-facing quickstart artifacts and update manifest.

    GA 1.0 v3 SS6: Integrates the full Explainability and Visualization
    Contract (XVC) artifact suite.
    """
    task_dir.mkdir(parents=True, exist_ok=True)
    if profile is None:
        profile = default_profile()

    # ── GA 1.0 Step 4: Auto-compute quality_decision for ga_full / forensic profiles ──
    if quality_decision is None and profile.name in ("ga_full", "forensic"):
        try:
            from docmirror.evidence.quality_decision import build_quality_decision

            quality_decision = build_quality_decision()
        except Exception:
            pass

    manifest["output_profile"] = profile.name
    manifest["schema_versions"] = _build_schema_versions()
    domain = _document_type_from_result(result) or str(manifest.get("document_type") or "generic")
    try:
        from docmirror.configs.ga_readiness import compact_domain_readiness

        manifest["domain_readiness"] = compact_domain_readiness(domain)
    except Exception:
        manifest["domain_readiness"] = {"domain": domain, "support_level": "unknown"}
    manifest.setdefault(
        "open_source_commitment",
        {
            "default_output": "edition_json_only",
            "artifact_pack": "opt_in",
            "purpose": "human_review_audit_and_issue_reproduction",
        },
    )

    artifacts = manifest.setdefault("artifacts", {})
    existing_roles = manifest.get("artifact_roles") or {}

    # output.md
    output_md = task_dir / "output.md"
    if profile.markdown and not output_md.exists():
        markdown_name = artifacts.get("markdown")
        markdown_path = task_dir / markdown_name if isinstance(markdown_name, str) else None
        if markdown_path and markdown_path.is_file():
            output_md.write_text(markdown_path.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            text = getattr(result, "full_text", "") if result is not None else ""
            output_md.write_text(
                text or "# DocMirror Output\n\nNo markdown content was generated.\n",
                encoding="utf-8",
            )
    if output_md.exists():
        artifacts.setdefault("quickstart_markdown", output_md.name)

    # quality_report.json v3
    if profile.quality_report:
        quality_report = _build_quality_report_v3(
            manifest,
            result=result,
            quality_decision=quality_decision,
            source_span_ledger=source_span_ledger,
        )
        quality_path = task_dir / "quality_report.json"
        quality_path.write_text(dumps_json(quality_report, ensure_ascii=False, indent=2), encoding="utf-8")
        artifacts["quality_report"] = quality_path.name

    # quality_decision.json
    if quality_decision is not None:
        qd_path = task_dir / "quality_decision.json"
        if hasattr(quality_decision, "to_dict"):
            qd_data = quality_decision.to_dict()
        elif isinstance(quality_decision, dict):
            qd_data = quality_decision
        else:
            qd_data = {"decision": str(quality_decision)}
        qd_path.write_text(dumps_json(qd_data, ensure_ascii=False, indent=2), encoding="utf-8")
        artifacts["quality_decision"] = qd_path.name

    # GA 1.0 SS4.12 N1 / G3: Embed quality_decision block into every
    # edition and mirror JSON artifact in the task directory.
    if quality_decision is not None:
        _embed_quality_decision_in_artifacts(task_dir, quality_decision)

    # visual_evidence_graph.json
    if visual_graph is not None and hasattr(visual_graph, "to_dict"):
        veg_path = task_dir / "visual_evidence_graph.json"
        veg_path.write_text(
            dumps_json(visual_graph.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        artifacts["visual_evidence_graph"] = veg_path.name

    # overlay_manifest.json
    if overlay_manifest is not None:
        om_path = task_dir / "overlay_manifest.json"
        om_path.write_text(dumps_json(overlay_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        artifacts["overlay_manifest"] = om_path.name

    # source_span_ledger.json
    if source_span_ledger is not None and hasattr(source_span_ledger, "to_dict"):
        ssl_path = task_dir / "source_span_ledger.json"
        ssl_path.write_text(
            dumps_json(source_span_ledger.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        artifacts["source_span_ledger"] = ssl_path.name

    # evidence/
    if profile.evidence_bundle:
        evidence_dir = task_dir / "evidence"
        evidence_dir.mkdir(exist_ok=True)
        (evidence_dir / "README.md").write_text(
            "# DocMirror Evidence\n\nThis folder is reserved for crops, overlays, diffs, and minimal repro data.\n",
            encoding="utf-8",
        )
        artifacts.setdefault("evidence_dir", evidence_dir.name)

    # Page images (W2-03) and layout overlay PDF (W2-05)
    if pdf_path and Path(pdf_path).exists():
        try:
            from docmirror.output.internal.page_image_renderer import render_page_images as _render_images

            page_img_dir = task_dir / "page_images"
            _render_images(pdf_path, page_img_dir, dpi=150)
            artifacts["page_images"] = str(page_img_dir)
        except Exception:
            pass

    # visual_debug.html (v3 static visualizer)
    if profile.visual_debug:
        visual_path = task_dir / "visual_debug.html"
        html_content = _build_visual_debug_html_v3(
            manifest,
            visual_graph=visual_graph,
            overlay_manifest=overlay_manifest,
            quality_decision=quality_decision,
        )
        visual_path.write_text(html_content, encoding="utf-8")
        artifacts["visual_debug"] = visual_path.name

    # artifact_roles
    roles = _build_artifact_roles(manifest)
    if existing_roles:
        roles = {**existing_roles, **{k: v for k, v in roles.items() if v}}
    manifest["artifact_roles"] = roles
    manifest["artifacts"] = artifacts
    return manifest


def _document_type_from_result(result: Any | None) -> str:
    if result is None:
        return ""
    entities = getattr(result, "entities", None)
    if entities is not None:
        doc_type = getattr(entities, "document_type", "")
        if doc_type:
            return str(doc_type)
    mirror = getattr(result, "mirror", None)
    if isinstance(mirror, dict):
        doc_type = (mirror.get("document") or {}).get("document_type")
        if doc_type:
            return str(doc_type)
    return ""


def _embed_quality_decision_in_artifacts(
    task_dir: Path,
    quality_decision: Any,
) -> None:
    """Embed quality_decision block into edition and mirror JSON artifacts.

    GA 1.0 SS4.12 N1: Every Edition JSON and Mirror JSON must carry a
    top-level ``quality_decision`` block so users can programmatically
    check decision status without running separate quality tools.

    Scans the task directory for JSON files that look like artifacts
    (edition_*.json, *_mirror.json, community.json, etc.) and adds or
    updates the ``quality_decision`` key.
    """
    qd_data: dict[str, Any]
    if hasattr(quality_decision, "to_dict"):
        qd_data = quality_decision.to_dict()
    elif isinstance(quality_decision, dict):
        qd_data = quality_decision
    else:
        return

    import json as _json

    # Find candidate JSON files — exclude quality_decision.json and quality_report.json
    skip_names = {
        "quality_decision.json",
        "quality_report.json",
        "output.md",
        "visual_debug.html",
        "manifest.json",
        "visual_evidence_graph.json",
        "overlay_manifest.json",
        "source_span_ledger.json",
        "schema_versions.json",
    }
    candidate_suffixes = {
        "_mirror.json",
        "_edition.json",
        "_community.json",
        "_enterprise.json",
        "_finance.json",
        "community.json",
        "enterprise.json",
        "finance.json",
        "mirror.json",
    }

    for fpath in sorted(task_dir.glob("*.json")):
        name = fpath.name
        if name in skip_names:
            continue
        # Only process files that look like edition/mirror artifacts
        if not any(name.endswith(suf) or name == suf.lstrip("_") for suf in candidate_suffixes):
            continue
        try:
            data = _json.loads(fpath.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue
            data["quality_decision"] = qd_data
            fpath.write_text(
                dumps_json(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass


def _build_quality_report_v3(
    manifest: dict[str, Any],
    *,
    result: Any | None = None,
    quality_decision: Any | None = None,
    source_span_ledger: Any | None = None,
) -> dict[str, Any]:
    """Build quality_report.json v3 using observed metrics only.

    No static claims -- all claims derive from observed evidence.
    """
    quality_summary = manifest.get("quality_summary") or {}
    edition_availability = manifest.get("edition_availability") or {}
    errors = manifest.get("errors") or []
    output_profile = manifest.get("output_profile", "quickstart")
    artifacts = manifest.get("artifacts") or {}
    parser_options = manifest.get("parser_options", {})
    if result is not None and hasattr(result, "parser_info") and result.parser_info:
        parser_options = (result.parser_info.options or {}) if hasattr(result.parser_info, "options") else {}

    decision = "not_computed"
    decision_reason = ""
    needs_review: list[dict[str, Any]] = []
    if quality_decision is not None:
        decision = (
            quality_decision.decision
            if hasattr(quality_decision, "decision")
            else quality_decision.get("decision", "not_computed")
        )
        decision_reason = (
            quality_decision.decision_reason
            if hasattr(quality_decision, "decision_reason")
            else quality_decision.get("decision_reason", "")
        )
        nr = (
            quality_decision.needs_review
            if hasattr(quality_decision, "needs_review")
            else quality_decision.get("needs_review", [])
        )
        for item in nr:
            needs_review.append(item.to_dict() if hasattr(item, "to_dict") else dict(item))

    if errors:
        needs_review.append({"scope": "task", "reason": "errors_present", "count": len(errors)})
    input_quality = parser_options.get("input_quality", {})
    if input_quality.get("low_quality_warning"):
        needs_review.append(
            {
                "scope": "input_quality",
                "reason": "low_quality_image",
                "score": input_quality.get("image_score"),
            }
        )
    for edition, item in edition_availability.items():
        if isinstance(item, dict) and item.get("status") in {"degraded", "unavailable", "skipped"}:
            needs_review.append(
                {
                    "scope": edition,
                    "reason": item.get("reason") or item.get("status"),
                }
            )

    span_summary: dict[str, Any] = {}
    if source_span_ledger is not None and hasattr(source_span_ledger, "summary"):
        span_summary = source_span_ledger.summary

    has_markdown = bool(artifacts.get("markdown") or artifacts.get("quickstart_markdown"))
    has_edition = bool(
        edition_availability.get("community")
        and edition_availability["community"].get("status") in {"written", "available"}
    )
    has_evidence = bool(artifacts.get("evidence"))

    observability = manifest.get("observability") or {}
    integration = {
        "request_id": manifest.get("request_id") or observability.get("request_id", ""),
        "version": observability.get("version", __version__),
        "profile": observability.get("profile") or manifest.get("output_profile", "full"),
        "entry": observability.get("entry", "unknown"),
    }

    return {
        "version": 3,
        "task_id": manifest.get("task_id"),
        "document_id": manifest.get("document_id"),
        "request_id": integration["request_id"],
        "output_profile": output_profile,
        "integration": integration,
        "decision": decision,
        "decision_reason": decision_reason,
        "readiness": {
            "human_readable_markdown": "pass" if has_markdown else "fail",
            "system_readable_edition": "pass" if has_edition else "fail",
            "audit_readable_evidence": "pass" if has_evidence else "partial",
        },
        "quality_summary": quality_summary,
        "edition_availability": edition_availability,
        "needs_review": needs_review,
        "input_quality": input_quality if input_quality else None,
        "source_span_coverage": span_summary,
        "observed_metrics": manifest.get("ga_metric_observations") or {},
    }


def _build_visual_debug_html_v3(
    manifest: dict[str, Any],
    *,
    visual_graph: Any | None = None,
    overlay_manifest: dict[str, Any] | None = None,
    quality_decision: Any | None = None,
) -> str:
    """Build the v3 self-contained static visual_debug.html.

    Embeds visual_evidence_graph and overlay_manifest data inline so the
    file works offline with no web server.
    """
    doc_id = escape(str(manifest.get("document_id", "")))
    task_id = escape(str(manifest.get("task_id", "")))
    profile = escape(str(manifest.get("output_profile", "quickstart")))
    decision = "not_computed"
    if quality_decision is not None:
        decision = (
            quality_decision.decision
            if hasattr(quality_decision, "decision")
            else quality_decision.get("decision", "not_computed")
        )

    veg_json = "{}"
    if visual_graph is not None and hasattr(visual_graph, "to_dict"):
        veg_json = dumps_json(visual_graph.to_dict(), ensure_ascii=False)
    om_json = "{}"
    if overlay_manifest is not None:
        om_json = dumps_json(overlay_manifest, ensure_ascii=False)

    css = _read_template("visual_debug.css")
    js = _read_template("visual_debug.js")

    decision_class = (
        "decision-auto"
        if decision == "auto_ingest"
        else ("decision-review" if decision == "needs_review" else "decision-reject")
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>DocMirror Visual Debug</title>
<style>
{css}
</style>
</head>
<body>
<div id="top-bar">
  <div class="top-left">
    <span class="doc-id">{doc_id}</span>
    <span class="sep">|</span>
    <span class="task-id">{task_id}</span>
  </div>
  <div class="top-center">
    <span class="profile-badge">{profile}</span>
    <span class="decision-badge {decision_class}">{decision}</span>
  </div>
  <div class="top-right">
    <span class="artifact-link" title="visual_evidence_graph.json">VEG</span>
    <span class="artifact-link" title="overlay_manifest.json">OLM</span>
    <span class="artifact-link" title="quality_report.json">QR</span>
  </div>
</div>
<div id="main-layout">
  <div id="left-sidebar">
    <div id="page-list"></div>
  </div>
  <div id="center-pane">
    <div id="canvas-container">
      <img id="page-image" src="" alt="Page" style="display:none" />
      <svg id="overlay-svg" width="800" height="1100"></svg>
    </div>
    <div id="layer-bar"></div>
  </div>
  <div id="right-sidebar">
    <div id="inspector-panel">
      <div id="inspector-empty">Click an overlay to inspect</div>
      <div id="inspector-content" style="display:none"></div>
    </div>
  </div>
</div>
<script>
window.VISUAL_EVIDENCE_GRAPH = {veg_json};
window.OVERLAY_MANIFEST = {om_json};
</script>
<script>
{js}
</script>
</body>
</html>"""


__all__ = [
    "ensure_quickstart_artifact_pack",
    "_build_quality_report_v3",
    "_build_visual_debug_html_v3",
]
