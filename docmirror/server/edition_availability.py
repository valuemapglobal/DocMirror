# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Edition availability manifest helpers."""

from __future__ import annotations

import importlib
from typing import Any

from docmirror.configs.ga_readiness import compact_domain_readiness, edition_sku_status


def edition_package_available(edition: str) -> bool:
    if edition in {"mirror", "community"}:
        return True
    try:
        importlib.import_module(f"docmirror_{edition}")
        return True
    except ImportError:
        return False


def build_edition_availability(
    requested: tuple[str, ...] | list[str],
    written: dict[str, Any] | None = None,
    projections: dict[str, Any] | None = None,
    document_type: str = "",
) -> dict[str, dict[str, Any]]:
    req = tuple("mirror" if ed == "json" else ed for ed in requested)
    if "all" in req:
        req = ("mirror", "community", "enterprise", "finance")
    written = written or {}
    projections = projections or {}
    out: dict[str, dict[str, Any]] = {}
    for edition in ("mirror", "community", "enterprise", "finance"):
        is_requested = edition in req
        payload = projections.get(edition)
        item: dict[str, Any] = {
            "requested": is_requested,
            "sku_status": edition_sku_status(document_type, edition),
        }
        if edition == "community":
            item["domain_readiness"] = compact_domain_readiness(document_type)
        if not is_requested:
            item["status"] = "not_requested"
        elif _payload_has_license_degrade(payload):
            item.update({"status": "degraded", "reason": "license_missing", "fallback": "community"})
        elif edition in written:
            item["status"] = "written"
        elif edition in {"enterprise", "finance"} and not edition_package_available(edition):
            item.update(
                {
                    "status": "unavailable",
                    "reason": "package_missing",
                    "package": f"docmirror_{edition}",
                }
            )
        elif payload is None:
            item.update({"status": "skipped", "reason": "no_payload"})
        else:
            item["status"] = "available"
        out[edition] = item
    return out


def _payload_has_license_degrade(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    warnings = (payload.get("status") or {}).get("warnings") or []
    composition = payload.get("composition") or {}
    return "_license_warning" in warnings or composition.get("reason") == "license_degrade"
