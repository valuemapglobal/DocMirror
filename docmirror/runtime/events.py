# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""DRC Progress Event Ledger — real progress events, fallback events, metric events.

GA 1.0 §6.3: The Progress Event Ledger is the single source of truth for task
progress. Events are written as ndjson and consumed by CLI progress bars,
REST endpoints, and SDK callbacks.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal


EventStatus = Literal["started", "succeeded", "failed_retryable", "failed_final", "skipped"]


@dataclass
class ProgressEvent:
    """A single progress event from a work unit execution.

    Written to ``progress_events.ndjson`` as one JSON line per event.
    """

    event_id: str = ""
    task_id: str = ""
    file_id: str = ""
    work_unit_id: str = ""
    stage: str = ""  # page_extract, page_enrich, cross_page_merge, chunk_project, etc.
    status: EventStatus = "started"
    progress: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""
    message: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.event_id:
            self.event_id = f"evt_{uuid.uuid4().hex[:12]}"
        if not self.timestamp:
            self.timestamp = _utc_now_iso()

    def to_ndjson(self) -> str:
        import json
        return json.dumps(_serializable(self), ensure_ascii=False) + "\n"


@dataclass
class FallbackEvent:

    def to_dict(self) -> dict[str, Any]:
        """Serialize FallbackEvent to a dict matching the DRC contract schema."""
        import json
        return _serializable(self)

    """Records a runtime fallback from one path to another.

    e.g., VLM unavailable → CPU OCR; GPU missing → CPU extraction.
    """

    event_id: str = ""
    task_id: str = ""
    fallback_type: str = ""  # vlm_unavailable, gpu_missing, provider_timeout
    from_path: str = ""
    to_path: str = ""
    reason: str = ""
    scope: dict[str, Any] = field(default_factory=dict)  # {"file_id": "001", "page": 3}
    effect: str = ""  # slower_parse, lower_confidence, reduced_evidence
    user_visible: bool = True
    timestamp: str = ""

    def __post_init__(self):
        if not self.event_id:
            self.event_id = f"fallback_{uuid.uuid4().hex[:12]}"
        if not self.timestamp:
            self.timestamp = _utc_now_iso()

    def to_ndjson(self) -> str:
        import json
        return json.dumps(_serializable(self), ensure_ascii=False) + "\n"


@dataclass

class MetricEvent:
    """Records a single runtime metric data point."""

    event_id: str = ""
    task_id: str = ""
    file_id: str = ""
    metric_name: str = ""
    metric_value: float = 0.0
    tags: dict[str, str] = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self):
        if not self.event_id:
            self.event_id = f"metric_{uuid.uuid4().hex[:12]}"
        if not self.timestamp:
            self.timestamp = _utc_now_iso()

    def to_ndjson(self) -> str:
        import json
        return json.dumps(_serializable(self), ensure_ascii=False) + "\n"


def _utc_now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _serializable(obj: Any) -> dict[str, Any]:
    """Convert dataclass to a dict safe for JSON serialization."""
    if hasattr(obj, "__dataclass_fields__"):
        result: dict[str, Any] = {}
        for f_name in obj.__dataclass_fields__:
            val = getattr(obj, f_name)
            # Handle nested dataclasses and lists
            if hasattr(val, "__dataclass_fields__"):
                result[f_name] = _serializable(val)
            elif isinstance(val, list):
                result[f_name] = [_serializable(v) if hasattr(v, "__dataclass_fields__") else v for v in val]
            elif isinstance(val, dict):
                result[f_name] = {k: _serializable(v) if hasattr(v, "__dataclass_fields__") else v for k, v in val.items()}
            else:
                result[f_name] = val
        return result
    return obj


__all__ = [
    "EventStatus",
    "FallbackEvent",
    "MetricEvent",
    "ProgressEvent",
]
