# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared semantic-solver result contract for plugin implementations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

DomainStatus = Literal["success", "needs_review", "degraded", "failed"]


@dataclass(frozen=True)
class DomainSolution:
    """Selected domain interpretation after invariant checks."""

    domain: str
    canonical_model: dict[str, Any] = field(default_factory=dict)
    selected_candidates: tuple[str, ...] = ()
    rejected_candidates: tuple[dict[str, Any], ...] = ()
    invariant_results: tuple[dict[str, Any], ...] = ()
    confidence: float = 0.0
    status: DomainStatus = "failed"
    diagnostics: tuple[dict[str, Any], ...] = ()

    @property
    def success(self) -> bool:
        return self.status == "success"


__all__ = ["DomainSolution", "DomainStatus"]
