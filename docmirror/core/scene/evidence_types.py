# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Evidence signal type for document classification."""


class Evidence:
    """A single evidence signal for document classification."""

    __slots__ = ("source", "category", "weight", "direction", "detail")

    def __init__(
        self,
        source: str,
        category: str,
        weight: float,
        direction: int,
        detail: str,
    ):
        self.source = source  # "keyword" / "header" / "entity" / "visual" / "metadata"
        self.category = category  # target category name
        self.weight = weight  # evidence strength 0.0-1.0 (or penalty magnitude for -1)
        self.direction = direction  # +1 support, -1 exclusion
        self.detail = detail  # human-readable explanation

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "category": self.category,
            "weight": round(self.weight, 3),
            "direction": self.direction,
            "detail": self.detail,
        }

    def __repr__(self) -> str:
        return (
            f"Evidence(source={self.source}, category={self.category}, "
            f"weight={self.weight:.3f}, direction={'+' if self.direction == 1 else '-'})"
        )
