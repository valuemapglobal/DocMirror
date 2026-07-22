# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Record projector outcomes in the delivery manifest without rechecking policy."""

from __future__ import annotations

from typing import Any

from docmirror.configs.ga_readiness import compact_domain_readiness, edition_sku_status


def build_edition_availability(
    *,
    written: dict[str, Any] | None = None,
    projections: dict[str, Any] | None = None,
    document_type: str = "",
) -> dict[str, dict[str, Any]]:
    written = written or {}
    projections = projections or {}
    projector_outcomes = projections.get("edition_availability") or {}
    out: dict[str, dict[str, Any]] = {}
    for edition in ("mirror", "community", "enterprise", "finance"):
        payload = projections.get(edition)
        item: dict[str, Any] = {
            "sku_status": edition_sku_status(document_type, edition),
        }
        if edition == "community":
            item["domain_readiness"] = compact_domain_readiness(document_type)
        if edition in written:
            item["status"] = "written"
        elif payload is not None:
            item["status"] = "available"
        elif isinstance(projector_outcomes.get(edition), dict):
            item.update(projector_outcomes[edition])
        elif edition in {"enterprise", "finance"}:
            item.update({"status": "unavailable", "reason": "projector_failed"})
        elif edition in projections:
            item.update({"status": "skipped", "reason": "no_payload"})
        else:
            item["status"] = "available"
        out[edition] = item
    return out
