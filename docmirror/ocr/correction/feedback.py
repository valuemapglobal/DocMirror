# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Reviewable JSONL feedback records; feedback never mutates production packs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class CorrectionFeedback:
    original: str
    candidate: str
    accepted: bool | None = None
    language: str | None = None
    country: str | None = None
    domain: str | None = None
    role: str = "unknown"
    rule_id: str | None = None
    source_ref: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "original": self.original,
            "candidate": self.candidate,
            "accepted": self.accepted,
            **({"language": self.language} if self.language else {}),
            **({"country": self.country} if self.country else {}),
            **({"domain": self.domain} if self.domain else {}),
            "role": self.role,
            **({"rule_id": self.rule_id} if self.rule_id else {}),
            **({"source_ref": self.source_ref} if self.source_ref else {}),
        }


def feedback_from_events(events: Iterable[dict[str, Any]]) -> list[CorrectionFeedback]:
    feedback: list[CorrectionFeedback] = []
    for event in events:
        if not isinstance(event, dict) or event.get("action") not in {"suggested", "applied"}:
            continue
        feedback.append(
            CorrectionFeedback(
                original=str(event.get("original") or ""),
                candidate=str(event.get("corrected") or ""),
                language=str(event.get("language") or "") or None,
                country=str(event.get("country") or "") or None,
                domain=str(event.get("domain") or "") or None,
                role=str(event.get("role") or "unknown"),
                rule_id=str(event.get("rule_id") or "") or None,
                source_ref=str(event.get("source_ref") or ""),
            )
        )
    return feedback


def write_feedback_jsonl(records: Iterable[CorrectionFeedback], path: str | Path) -> int:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    items = list(records)
    target.write_text(
        "".join(json.dumps(item.to_dict(), ensure_ascii=False, sort_keys=True) + "\n" for item in items),
        encoding="utf-8",
    )
    return len(items)


__all__ = ["CorrectionFeedback", "feedback_from_events", "write_feedback_jsonl"]
