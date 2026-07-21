# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Read canonical evidence from ParseResult without a Mirror projection."""

from __future__ import annotations

from typing import Any


def evidence_payload(parse_result: Any) -> dict[str, Any]:
    plane = getattr(parse_result, "evidence_plane", None)
    evidence = getattr(plane, "evidence", None)
    if evidence is None:
        return {}
    if hasattr(evidence, "model_dump"):
        return evidence.model_dump(mode="json", exclude_none=True)
    return dict(evidence) if isinstance(evidence, dict) else {}


def text_atoms(parse_result: Any) -> list[dict[str, Any]]:
    atoms = evidence_payload(parse_result).get("text_atoms") or []
    return [item for item in atoms if isinstance(item, dict)]


__all__ = ["evidence_payload", "text_atoms"]
