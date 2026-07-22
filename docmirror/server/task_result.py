# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""TaskResult contract shared by CLI/API/SDK.

GA 1.0 DRC §6.5: TaskResult v2 adds runtime fields (stage, progress,
runtime, intermediate_artifacts, page_outcomes, chunk_outcomes, fallbacks,
metrics) while preserving the stable v1 field shape."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


class TaskResult(BaseModel):
    task_id: str
    status: Literal["success", "partial", "failed", "running"] = "success"
    inputs: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: dict[str, str] = Field(default_factory=dict)
    edition_availability: dict[str, Any] = Field(default_factory=dict)
    pipeline_decision: dict[str, Any] = Field(default_factory=dict)
    mirror_completeness: dict[str, Any] = Field(default_factory=dict)
    quality_summary: dict[str, Any] = Field(default_factory=dict)
    errors: list[dict[str, Any]] = Field(default_factory=list)

    # ── v2 additive fields (DRC §6.5) ──
    version: int = Field(default=2, description="Manifest version (1 or 2)")
    stage: str = Field(default="", description="Current execution stage")
    progress: dict[str, Any] = Field(default_factory=dict, description="Aggregate progress from work units")
    runtime: dict[str, Any] = Field(default_factory=dict, description="Runtime control snapshot")
    intermediate_artifacts: dict[str, Any] = Field(
        default_factory=dict, description="Page/chunk intermediate artifact index"
    )
    page_outcomes: list[dict[str, Any]] = Field(
        default_factory=list, description="Per-page success/failed/skipped outcomes"
    )
    chunk_outcomes: list[dict[str, Any]] = Field(default_factory=list, description="Per-chunk outcomes")
    fallbacks: list[dict[str, Any]] = Field(default_factory=list, description="Fallback event ledger")
    metrics: dict[str, Any] = Field(default_factory=dict, description="Runtime metrics snapshot")

    # v2 explainability fields (XVC W6-03)
    artifact_roles: dict[str, str] = Field(
        default_factory=dict, description="Artifact role mapping for explainability consumers"
    )
    explainability_summary: dict[str, Any] = Field(
        default_factory=dict,
        description="Explainability summary: visual status, quality decision, diff link, support link",
    )
    visual_debug_path: str = Field(default="", description="Path to visual_debug.html")
    visual_evidence_graph_path: str = Field(default="", description="Path to visual_evidence_graph.json")
    source_span_ledger_path: str = Field(default="", description="Path to source_span_ledger.json")
    quality_decision_path: str = Field(default="", description="Path to quality_decision.json")
    diff_report_path: str = Field(default="", description="Path to diff_report.json")
    support_bundle_path: str = Field(default="", description="Path to support_bundle.zip")

    def public_dict(self) -> dict[str, Any]:
        """Return the compact transport contract shared by CLI/API/SDK.

        Full runtime and diagnostic fields remain available in ``manifest.json``.
        In particular, the public task representation never exposes Mirror
        content or diagnostic filesystem paths.
        """
        payload = self.model_dump(
            include={
                "version",
                "task_id",
                "status",
                "stage",
                "progress",
                "inputs",
                "artifacts",
                "edition_availability",
                "quality_summary",
                "errors",
            },
            mode="json",
        )
        payload["artifacts"] = {
            role: path
            for role, path in payload.get("artifacts", {}).items()
            if role != "mirror" and not role.endswith("_mirror")
        }
        payload["edition_availability"] = _without_mirror(payload.get("edition_availability", {}))
        for item in payload.get("inputs", []):
            if isinstance(item.get("artifacts"), dict):
                item["artifacts"] = {
                    role: path
                    for role, path in item["artifacts"].items()
                    if role != "mirror" and not role.endswith("_mirror")
                }
            if isinstance(item.get("edition_availability"), dict):
                item["edition_availability"] = _without_mirror(item["edition_availability"])
        return payload


def _without_mirror(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _without_mirror(item) for key, item in value.items() if key != "mirror"}
    if isinstance(value, list):
        return [_without_mirror(item) for item in value]
    return value


def task_result_from_manifest(path: str | Path) -> TaskResult:
    import json

    manifest_path = Path(path)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors_list = data.get("errors") or []
    status = data.get("status") or ("failed" if errors_list else "success")
    version = data.get("version", 1)
    return TaskResult(
        task_id=str(data.get("task_id") or manifest_path.parent.name),
        status=status,
        inputs=list(data.get("inputs") or ([data.get("input") or {}] if data.get("input") is not None else [])),
        artifacts={k: v for k, v in (data.get("artifacts") or {}).items() if isinstance(v, str)},
        edition_availability=data.get("edition_availability") or {},
        pipeline_decision=data.get("pipeline_decision") or {},
        mirror_completeness=data.get("mirror_completeness") or {},
        quality_summary=data.get("quality_summary") or {},
        errors=errors_list,
        version=version,
        stage=data.get("stage", ""),
        progress=data.get("progress") or {},
        runtime=data.get("runtime") or {},
        intermediate_artifacts=data.get("intermediate_artifacts") or {},
        page_outcomes=data.get("page_outcomes") or [],
        chunk_outcomes=data.get("chunk_outcomes") or [],
        fallbacks=data.get("fallbacks") or [],
        metrics=data.get("metrics") or {},
        artifact_roles=data.get("artifact_roles") or {},
        explainability_summary=data.get("explainability_summary") or {},
        visual_debug_path=data.get("visual_debug_path", ""),
        visual_evidence_graph_path=data.get("visual_evidence_graph_path", ""),
        source_span_ledger_path=data.get("source_span_ledger_path", ""),
        quality_decision_path=data.get("quality_decision_path", ""),
        diff_report_path=data.get("diff_report_path", ""),
        support_bundle_path=data.get("support_bundle_path", ""),
    )
