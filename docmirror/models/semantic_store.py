# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Semantic SSOT store for edition/reasoning-only facts.

This is intentionally an in-memory contract object first. Persistence can be
added behind the same API once semantic fields stabilize.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from docmirror.models.mirror.semantic_contract import partition_domain_specific


@dataclass(frozen=True)
class SemanticRecord:
    """One semantic fact that must not be written back into Mirror facts."""

    key: str
    value: Any
    source: str = "domain_specific"
    edition: str = "community"
    evidence_refs: tuple[str, ...] = ()


@dataclass
class SemanticStore:
    """Small semantic source-of-truth container keyed by edition and field."""

    records: dict[tuple[str, str], SemanticRecord] = field(default_factory=dict)

    def put(self, record: SemanticRecord) -> None:
        self.records[(record.edition, record.key)] = record

    def get(self, key: str, *, edition: str = "community") -> SemanticRecord | None:
        return self.records.get((edition, key))

    def project(self, *, edition: str | None = None) -> dict[str, Any]:
        return {
            key: record.value
            for (record_edition, key), record in sorted(self.records.items())
            if edition is None or record_edition == edition
        }

    @classmethod
    def from_domain_specific(
        cls,
        domain_specific: dict[str, Any] | None,
        *,
        edition: str = "community",
        source: str = "domain_specific",
    ) -> SemanticStore:
        _mirror, semantic = partition_domain_specific(domain_specific)
        store = cls()
        for key, value in semantic.items():
            store.put(SemanticRecord(key=key, value=value, source=source, edition=edition))
        return store


__all__ = [
    "SemanticRecord",
    "SemanticStore",
]
