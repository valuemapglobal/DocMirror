# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed contracts for conservative OCR post-correction decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

CorrectionAction = Literal["unchanged", "applied", "suggested"]
CorrectionMode = Literal["off", "safe", "suggest"]


@dataclass(frozen=True)
class CorrectionContext:
    """Evidence available when deciding whether a text mutation is safe."""

    role: str = "unknown"
    domain: str | None = None
    source_ref: str = ""
    ocr_confidence: float | None = None
    mode: CorrectionMode = "safe"
    language: str | None = None
    country: str | None = None
    locale: str | None = None
    script: str | None = None
    pack_ids: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CorrectionDecision:
    """One auditable correction decision.

    ``corrected`` contains the best deterministic candidate.  Consumers must
    use :attr:`output_text`; suggestions deliberately preserve the input.
    """

    original: str
    corrected: str
    action: CorrectionAction = "unchanged"
    rule_id: str | None = None
    reason_codes: tuple[str, ...] = ()
    score: float = 1.0
    source_ref: str = ""
    role: str = "unknown"
    domain: str | None = None
    ocr_confidence: float | None = None
    candidates: tuple[str, ...] = ()
    pack_id: str | None = None
    pack_version: int | None = None
    language: str | None = None
    country: str | None = None
    locale: str | None = None
    script: str | None = None
    runner_up_score: float | None = None
    confidence_margin: float | None = None
    selected_pack_ids: tuple[str, ...] = ()
    selected_packs: tuple[tuple[str, int], ...] = ()

    @property
    def output_text(self) -> str:
        return self.corrected if self.action == "applied" else self.original

    @property
    def changed(self) -> bool:
        return self.corrected != self.original

    def to_dict(self) -> dict[str, Any]:
        return {
            "original": self.original,
            "corrected": self.corrected,
            "action": self.action,
            **({"rule_id": self.rule_id} if self.rule_id else {}),
            "reason_codes": list(self.reason_codes),
            "score": round(float(self.score), 4),
            **({"source_ref": self.source_ref} if self.source_ref else {}),
            "role": self.role,
            **({"domain": self.domain} if self.domain else {}),
            **({"ocr_confidence": round(float(self.ocr_confidence), 4)} if self.ocr_confidence is not None else {}),
            **({"candidates": list(self.candidates)} if self.candidates else {}),
            **({"pack_id": self.pack_id} if self.pack_id else {}),
            **({"pack_version": self.pack_version} if self.pack_version is not None else {}),
            **({"language": self.language} if self.language else {}),
            **({"country": self.country} if self.country else {}),
            **({"locale": self.locale} if self.locale else {}),
            **({"script": self.script} if self.script else {}),
            **({"runner_up_score": round(float(self.runner_up_score), 4)} if self.runner_up_score is not None else {}),
            **(
                {"confidence_margin": round(float(self.confidence_margin), 4)}
                if self.confidence_margin is not None
                else {}
            ),
            **({"selected_pack_ids": list(self.selected_pack_ids)} if self.selected_pack_ids else {}),
            **(
                {
                    "selected_packs": [
                        {"pack_id": pack_id, "version": version} for pack_id, version in self.selected_packs
                    ]
                }
                if self.selected_packs
                else {}
            ),
        }


__all__ = [
    "CorrectionAction",
    "CorrectionContext",
    "CorrectionDecision",
    "CorrectionMode",
]
