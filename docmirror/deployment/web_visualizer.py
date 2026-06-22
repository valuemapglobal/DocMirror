"""Web Visualizer contract for DocMirror REST API (DIC-23).

Provides a standards-based web visualizer entry point that renders
task results with field-level evidence tracing.  Replaces the old
static ``visual_debug.html`` placeholder with a contract-driven
visualizer that can be served directly from the REST API.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>DocMirror Visualizer — {{title}}</title>
  <style>
    :root { --bg: #0d1117; --fg: #c9d1d9; --accent: #58a6ff; --border: #30363d;
            --success: #3fb950; --warn: #d2991d; --fail: #f85149; }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, sans-serif;
           background: var(--bg); color: var(--fg); padding: 24px; }
    h1 { color: var(--accent); margin-bottom: 16px; }
    .meta { display: grid; grid-template-columns: 180px 1fr; gap: 4px 12px;
            margin-bottom: 24px; }
    .meta dt { color: #8b949e; text-align: right; }
    .meta dd { font-family: monospace; }
    .status-success { color: var(--success); }
    .status-partial { color: var(--warn); }
    .status-failed { color: var(--fail); }
    table { border-collapse: collapse; width: 100%; margin: 16px 0; }
    th, td { border: 1px solid var(--border); padding: 8px 12px;
             text-align: left; font-size: 13px; }
    th { background: #161b22; }
    .artifact-link { color: var(--accent); text-decoration: none; }
    .artifact-link:hover { text-decoration: underline; }
    .evidence-badge { font-size: 11px; padding: 2px 6px; border-radius: 4px;
                       background: #1f6feb22; color: var(--accent); }
    .warn-badge { background: #d2991d22; color: var(--warn); }
    .section { margin-top: 24px; border-top: 1px solid var(--border);
               padding-top: 16px; }
  </style>
</head>
<body>
  <h1>DocMirror Visualizer</h1>
  <dl class="meta">
    <dt>Request ID</dt><dd>{{request_id}}</dd>
    <dt>Task ID</dt><dd>{{task_id}}</dd>
    <dt>Status</dt><dd class="status-{{status_css}}">{{status}}</dd>
    <dt>Version</dt><dd>{{version}}</dd>
    <dt>Profile</dt><dd>{{profile}}</dd>
  </dl>

  <div class="section">
    <h2>Artifacts</h2>
    <table>
      <tr><th>Role</th><th>File</th><th>Size</th></tr>
      {{artifact_rows}}
    </table>
  </div>

  <div class="section">
    <h2>Warnings{{warning_count}}</h2>
    {{warning_list}}
  </div>

  <div class="section">
    <h2>Quality Summary</h2>
    {{quality_block}}
  </div>

  <div class="section">
    <h2>Evidence Trace</h2>
    {{evidence_block}}
  </div>
</body>
</html>
"""


def build_visualizer_html(
    manifest: dict[str, Any],
    task_dir: str | Path | None = None,
) -> str:
    """Build a standards-compliant web visualizer HTML page from task metadata.

    Args:
        manifest: Task manifest dict (from manifest.json).
        task_dir: Optional path to task directory for artifact file listing.

    Returns:
        HTML string ready for serving via ``GET /v1/visualize/{task_id}``.
    """
    status = manifest.get("status", "unknown")
    status_css = {"success": "success", "partial": "partial", "failed": "failed"}.get(
        status, "partial"
    )

    # Artifact rows
    artifacts: dict = manifest.get("artifacts", {})
    rows = ""
    for role, filename in sorted(artifacts.items()):
        rows += f"<tr><td><span class='evidence-badge'>{role}</span></td>"
        rows += f"<td><span class='artifact-link'>{filename}</span></td>"
        rows += "<td>-</td></tr>\n"
    if not rows:
        rows = "<tr><td colspan='3'>No artifacts found.</td></tr>"

    # Warnings
    warnings = manifest.get("warnings", [])
    wcnt = f" ({len(warnings)})" if warnings else ""
    wlist = "".join(f"<div class='warn-badge'>{w}</div>" for w in warnings) if warnings else "<p>None</p>"

    # Quality
    quality = manifest.get("quality_summary", manifest.get("quality", {}))
    qblock = ""
    if quality:
        qblock = "<table>"
        for key in ("confidence", "trust_score", "validation_passed", "elapsed_ms"):
            val = quality.get(key)
            if val is not None:
                qblock += f"<tr><th>{key}</th><td>{val}</td></tr>"
        qblock += "</table>"
    else:
        qblock = "<p>No quality data available.</p>"

    # Evidence
    evidence = manifest.get("evidence", {})
    eblock = ""
    if isinstance(evidence, dict) and evidence:
        eblock = "<table><tr><th>Field</th><th>Evidence ID</th><th>Page</th></tr>"
        for field, info in list(evidence.items())[:20]:
            pid = info.get("evidence_id", info.get("id", "-"))
            page = info.get("page", "-")
            eblock += f"<tr><td>{field}</td><td>{pid}</td><td>{page}</td></tr>"
        eblock += "</table>"
    else:
        eblock = "<p>No evidence trace available.</p>"

    html = (
        _TEMPLATE.replace("{{title}}", manifest.get("task_id", "Task"))
        .replace("{{request_id}}", manifest.get("request_id", "-"))
        .replace("{{task_id}}", manifest.get("task_id", "-"))
        .replace("{{status}}", status)
        .replace("{{status_css}}", status_css)
        .replace("{{version}}", manifest.get("version", {}).get("package", "-"))
        .replace("{{profile}}", manifest.get("observability", {}).get("profile", manifest.get("profile", "-")))
        .replace("{{artifact_rows}}", rows)
        .replace("{{warning_count}}", wcnt)
        .replace("{{warning_list}}", wlist)
        .replace("{{quality_block}}", qblock)
        .replace("{{evidence_block}}", eblock)
    )

    return html


def serve_visualizer(manifest_path: str | Path) -> str:
    """One-shot: read a manifest and return the visualizer HTML."""
    data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    return build_visualizer_html(data)
