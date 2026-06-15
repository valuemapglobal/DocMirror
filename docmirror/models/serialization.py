# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""JSON-safe conversion for API and debug payloads."""

from __future__ import annotations

import json
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any


def json_default(obj: Any) -> Any:
    """``json.dumps`` fallback for non-JSON-native objects."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    if isinstance(obj, Enum):
        return obj.value
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def to_json_safe(value: Any) -> Any:
    """Recursively coerce *value* to plain JSON-serializable Python types."""
    return json.loads(json.dumps(value, default=json_default))


def dumps_json(value: Any, *, ensure_ascii: bool = False, indent: int | None = None) -> str:
    """Serialize *value* to a JSON string after coercion."""
    return json.dumps(to_json_safe(value), ensure_ascii=ensure_ascii, indent=indent)


def assert_json_serializable(value: Any) -> None:
    """Raise ``TypeError`` if *value* cannot be JSON-encoded."""
    json.dumps(value, default=json_default)
