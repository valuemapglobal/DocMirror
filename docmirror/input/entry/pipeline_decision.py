# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Pipeline Decision Record helpers."""

from __future__ import annotations

from typing import Any

from docmirror.configs.format.models import FormatCapability
from docmirror.input.entry.options import ParseControl


def build_pipeline_decision(
    cap: FormatCapability,
    control: ParseControl,
    *,
    support: dict[str, Any] | None = None,
) -> dict[str, Any]:
    binding = cap.binding
    selected_path = [cap.id]
    if binding and binding.transcode:
        selected_path.append(f"transcode:{binding.transcode.tool}->{binding.transcode.target}")
    if binding and binding.adapter:
        selected_path.append(f"adapter:{binding.adapter.rsplit('.', 1)[-1]}")
    skipped_paths: list[dict[str, str]] = []
    if control.execution.ocr == "off":
        skipped_paths.append({"path": "ocr", "reason": "ocr_policy_off"})
    # slm path removed in v1.1 — superseded by LlmDocumentRestorer
    skipped_paths.append({"path": "vlm", "reason": "not_enabled"})
    return {
        "capability_id": cap.id,
        "transport": cap.transport,
        "content_model": cap.content_model,
        "capability_status": cap.status,
        "support": support or {},
        "parse_mode": control.mode,
        "enhance_mode": control.enhance_mode,
        "ocr_policy": control.execution.ocr,
        "selected_pages": control.pages.to_display(),
        "selected_path": selected_path,
        "skipped_paths": skipped_paths,
        "fallbacks": [],
        "resource_budget": {
            "workers": control.resource.workers,
            "page_executor": control.resource.page_executor,
        },
    }


def record_fallback(decision: dict[str, Any] | None, *, from_path: str, to_path: str, reason: str) -> None:
    if not isinstance(decision, dict):
        return
    fallbacks = decision.setdefault("fallbacks", [])
    fallbacks.append({"from": from_path, "to": to_path, "reason": reason})
    selected = decision.setdefault("selected_path", [])
    marker = f"fallback:{to_path}"
    if marker not in selected:
        selected.append(marker)


def record_skipped(decision: dict[str, Any] | None, *, path: str, reason: str) -> None:
    if not isinstance(decision, dict):
        return
    skipped = decision.setdefault("skipped_paths", [])
    skipped.append({"path": path, "reason": reason})


def record_probe_failure(decision: dict[str, Any] | None, *, transport: str, reason: str) -> None:
    """Record an input probe failure (PDF encrypted/damaged, image invalid, etc.) in the PDR."""
    if not isinstance(decision, dict):
        return
    failures = decision.setdefault("probe_failures", [])
    failures.append({"transport": transport, "reason": reason})


def record_resource_reject(
    decision: dict[str, Any] | None, *, gate: str, actual: float | int, limit: float | int
) -> None:
    """Record a resource gate rejection (file size, archive budget, pixel limit) in the PDR."""
    if not isinstance(decision, dict):
        return
    rejects = decision.setdefault("resource_rejects", [])
    rejects.append({"gate": gate, "actual": actual, "limit": limit})


def record_safety_reject(decision: dict[str, Any] | None, *, check: str, reason: str) -> None:
    """Record a safety gate rejection (encrypted, damaged, path traversal) in the PDR."""
    if not isinstance(decision, dict):
        return
    rejects = decision.setdefault("safety_rejects", [])
    rejects.append({"check": check, "reason": reason})


def record_adapter_empty(decision: dict[str, Any] | None, *, adapter: str, reason: str) -> None:
    """Record an adapter empty-result event in the PDR."""
    if not isinstance(decision, dict):
        return
    empties = decision.setdefault("adapter_empties", [])
    empties.append({"adapter": adapter, "reason": reason})


def record_quality_degrade(
    decision: dict[str, Any] | None, *, from_score: float, to_score: float, reason: str
) -> None:
    """Record a quality degradation event (OCR low-quality, fallback resolution drop) in the PDR."""
    if not isinstance(decision, dict):
        return
    degrades = decision.setdefault("quality_degrades", [])
    degrades.append({"from": from_score, "to": to_score, "reason": reason})
