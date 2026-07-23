# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Immutable canonical ``ParseResult`` snapshots.

``SealedParseResult`` stores only canonical serialized bytes and their digest.
It retains no reference to the mutable model that was sealed. Consumers obtain
isolated read views, so even a malicious or buggy projector cannot mutate the
snapshot or another projector's view.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from docmirror.models.entities.parse_result import ParseResult

SEALED_SCHEMA_VERSION = "docmirror.sealed_parse_result.v1"


@dataclass(frozen=True, slots=True)
class SealedParseResult:
    """Content-addressed immutable snapshot of the canonical fact model."""

    _canonical_json: bytes
    fingerprint: str
    schema_version: str = SEALED_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SEALED_SCHEMA_VERSION:
            raise ValueError(f"unsupported sealed schema: {self.schema_version}")
        actual = hashlib.sha256(self._canonical_json).hexdigest()
        if actual != self.fingerprint:
            raise ValueError("sealed ParseResult fingerprint mismatch")

    def to_read_view(self) -> ParseResult:
        """Materialize a new mutable copy for one read-only consumer."""
        return ParseResult.model_validate_json(self._canonical_json)

    def to_legacy_copy(self) -> ParseResult:
        """Compatibility alias; callers receive a detached copy, never the SSOT."""
        return self.to_read_view()

    def fact_fingerprint(self) -> str:
        """Return the deterministic fact digest, distinct from snapshot integrity."""
        return self.to_read_view().fact_fingerprint()

    @property
    def integrity_fingerprint(self) -> str:
        """Digest of the complete immutable snapshot bytes."""
        return self.fingerprint

    def verify_integrity(self) -> bool:
        return hashlib.sha256(self._canonical_json).hexdigest() == self.fingerprint

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        return self.to_read_view().model_dump(**kwargs)

    def model_dump_json(self, **kwargs: Any) -> str:
        return self.to_read_view().model_dump_json(**kwargs)

    def __getattr__(self, name: str) -> Any:
        """Read-compatibility shim backed by a fresh detached view per access."""
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self.to_read_view(), name)


def seal_parse_result(result: ParseResult | SealedParseResult) -> SealedParseResult:
    """Deep-snapshot a canonical result; sealing an existing snapshot is idempotent."""
    if isinstance(result, SealedParseResult):
        return result
    if not isinstance(result, ParseResult):
        raise TypeError(f"seal_parse_result expects ParseResult; got {type(result).__name__}")
    payload = result.model_dump(mode="json", exclude_none=False)
    canonical_json = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    fingerprint = hashlib.sha256(canonical_json).hexdigest()
    return SealedParseResult(_canonical_json=canonical_json, fingerprint=fingerprint)


__all__ = ["SEALED_SCHEMA_VERSION", "SealedParseResult", "seal_parse_result"]
