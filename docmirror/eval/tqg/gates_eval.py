# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Evaluate TQG gate specifications against actual values."""

from __future__ import annotations

from typing import Any


def resolve_dot_path(obj: Any, path: str) -> Any:
    """Resolve ``a.b.c`` on ParseResult-like objects or dicts."""
    cur = obj
    for part in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            cur = getattr(cur, part, None)
    return cur


def eval_gate(actual: Any, spec: dict[str, Any]) -> tuple[bool, str | None]:
    """Return (passed, failure_message)."""
    if "equals" in spec:
        ok = actual == spec["equals"]
        if not ok:
            return False, f"expected {spec['equals']!r}, got {actual!r}"
        return True, None
    if "in" in spec:
        ok = actual in spec["in"]
        if not ok:
            return False, f"expected one of {spec['in']!r}, got {actual!r}"
        return True, None
    if "min" in spec:
        try:
            ok = float(actual) >= float(spec["min"])
        except (TypeError, ValueError):
            ok = False
        if not ok:
            return False, f"expected >= {spec['min']}, got {actual!r}"
        return True, None
    if "max" in spec:
        try:
            ok = float(actual) <= float(spec["max"])
        except (TypeError, ValueError):
            ok = False
        if not ok:
            return False, f"expected <= {spec['max']}, got {actual!r}"
        return True, None
    if "max_issues" in spec:
        count = len(actual) if isinstance(actual, list) else int(actual or 0)
        ok = count <= int(spec["max_issues"])
        if not ok:
            return False, f"expected <= {spec['max_issues']} issues, got {count}"
        return True, None
    return True, None
