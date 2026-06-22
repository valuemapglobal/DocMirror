# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Page Outcome Ledger — QTC §6.5, W4-02.

Tracks per-page processing outcomes:
- success: page fully processed, all content extracted
- partial: page processed but some content failed (LOW_OCR_CONFIDENCE, etc.)
- failure: page could not be processed at all

Each page gets an outcome record with error_code when applicable.
The ledger ensures that partial failures don't silently discard successful pages.

Design reference: docs/design/GA1.0/08_accuracy_trust_ga_gap_closure_plan.md QTC-12
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PageOutcome:
    """Outcome for a single page in a document parse."""
    page: int = 0
    status: str = "success"  # success | partial | failure
    error_code: str | None = None
    warning: str = ""
    content_preserved: bool = True


@dataclass
class PageOutcomeLedger:
    """Complete page outcome ledger for a document parse.

    Tracks all page outcomes and provides aggregate statistics.
    """
    outcomes: list[PageOutcome] = field(default_factory=list)
    document_id: str = ""

    def add_outcome(
        self,
        page: int,
        status: str = "success",
        error_code: str | None = None,
        warning: str = "",
        content_preserved: bool = True,
    ) -> None:
        """Record a page outcome."""
        self.outcomes.append(PageOutcome(
            page=page,
            status=status,
            error_code=error_code,
            warning=warning,
            content_preserved=content_preserved,
        ))

    @property
    def total_pages(self) -> int:
        return len(self.outcomes)

    @property
    def success_count(self) -> int:
        return sum(1 for o in self.outcomes if o.status == "success")

    @property
    def partial_count(self) -> int:
        return sum(1 for o in self.outcomes if o.status == "partial")

    @property
    def failure_count(self) -> int:
        return sum(1 for o in self.outcomes if o.status == "failure")

    @property
    def retained_success_pages(self) -> bool:
        """Whether all successful pages have their content preserved."""
        return all(
            o.content_preserved
            for o in self.outcomes
            if o.status == "success"
        )

    @property
    def page_level_partial_retention(self) -> float:
        """Fraction of pages that retained their content (success + partial with content)."""
        if self.total_pages == 0:
            return 1.0
        retained = sum(1 for o in self.outcomes if o.content_preserved)
        return retained / self.total_pages

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for observation events."""
        return {
            "document_id": self.document_id,
            "total_pages": self.total_pages,
            "success_count": self.success_count,
            "partial_count": self.partial_count,
            "failure_count": self.failure_count,
            "retained_success_pages": self.retained_success_pages,
            "page_level_partial_retention": self.page_level_partial_retention,
            "outcomes": [
                {
                    "page": o.page,
                    "status": o.status,
                    "error_code": o.error_code,
                    "warning": o.warning,
                    "content_preserved": o.content_preserved,
                }
                for o in self.outcomes
            ],
        }

    def to_observation_partial_pages(self) -> list[dict[str, Any]]:
        """Export as the partial_pages format used in QualityObservationEvent."""
        return [
            {
                "page": o.page,
                "status": o.status,
                "error_code": o.error_code,
            }
            for o in self.outcomes
        ]
