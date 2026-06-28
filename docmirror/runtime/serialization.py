"""JSON-safe serialization helpers for DocMirror runtime and output paths."""

from __future__ import annotations

import json
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel


def to_json_safe(value: Any) -> Any:
    """Convert common Python/Pydantic objects into JSON-serializable values."""
    if isinstance(value, BaseModel):
        return to_json_safe(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(k): to_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_json_safe(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "model_dump"):
        return to_json_safe(value.model_dump(mode="json"))
    if hasattr(value, "__dict__"):
        return to_json_safe(vars(value))
    return str(value)


def dumps_json(value: Any, **kwargs: Any) -> str:
    """Dump a value as UTF-8 friendly JSON after coercing unsupported objects."""
    kwargs.setdefault("ensure_ascii", False)
    return json.dumps(to_json_safe(value), **kwargs)


def assert_json_serializable(value: Any) -> None:
    """Raise if a value cannot be converted to JSON."""
    json.dumps(to_json_safe(value), ensure_ascii=False)
