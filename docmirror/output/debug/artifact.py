"""Debug artifact builder for optional forensic/development output."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from docmirror.output.serialization import dumps_json, to_json_safe


def is_debug_mode() -> bool:
    """Return whether debug-only output should be emitted."""
    return os.environ.get("DOCMIRROR_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}


def _annex_payload(result: Any) -> dict[str, Any]:
    annex = getattr(result, "annex", None)
    if annex is None:
        return {}
    payload = to_json_safe(annex)
    return payload if isinstance(payload, dict) else {"annex": payload}


def build_debug_artifact(result: Any) -> dict[str, Any]:
    """Build a JSON-safe debug artifact from a parse result."""
    artifact: dict[str, Any] = {}
    artifact.update(_annex_payload(result))

    for name in (
        "sections",
        "table_operations",
        "parser_info",
        "diagnostics",
        "metadata",
    ):
        value = getattr(result, name, None)
        if value:
            artifact[name] = to_json_safe(value)

    entities = getattr(result, "entities", None)
    if entities is not None:
        artifact["entities"] = to_json_safe(entities)
    return artifact


def write_debug_artifact(result: Any, path: str | Path) -> Path:
    """Write a debug artifact JSON file."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(dumps_json(build_debug_artifact(result), indent=2), encoding="utf-8")
    return out
