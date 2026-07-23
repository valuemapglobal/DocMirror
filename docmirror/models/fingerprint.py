# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deterministic fingerprints derived from canonical facts.

The fact view deliberately excludes execution, audit-clock, licensing, and
delivery concerns. It is a derived digest, never a retained model or another
source of truth.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

_FACT_FIELDS = (
    "status",
    "confidence",
    "error",
    "pages",
    "logical_tables",
    "document_flow",
    "evidence_plane",
    "entities",
    "trust",
    "provenance",
    "raw_text",
    "sections",
)


def canonical_fact_payload(result: Any) -> dict[str, Any]:
    """Return the normative fact-only view used for determinism checks."""
    dumped = result.model_dump(mode="json", exclude_none=False)
    payload = {field: dumped.get(field) for field in _FACT_FIELDS}

    provenance = payload.get("provenance")
    if isinstance(provenance, dict):
        # Content identity is factual; the caller-owned location is not.
        provenance = dict(provenance)
        provenance.pop("file_path", None)
        payload["provenance"] = provenance

    evidence_plane = payload.get("evidence_plane")
    if isinstance(evidence_plane, dict):
        # Evidence atoms are facts. Runtime collection diagnostics are not.
        evidence_plane = dict(evidence_plane)
        evidence_plane.pop("diagnostics", None)
        source = evidence_plane.get("source")
        if isinstance(source, dict):
            source = dict(source)
            source_provenance = source.get("provenance")
            if isinstance(source_provenance, dict):
                source_provenance = dict(source_provenance)
                # InputAcceptance may use a different private staging path on
                # every invocation. Content identity remains in sha256.
                source_provenance.pop("path", None)
                source_provenance.pop("file_path", None)
                source["provenance"] = source_provenance
            evidence_plane["source"] = source
        payload["evidence_plane"] = evidence_plane

    entities = payload.get("entities")
    if isinstance(entities, dict):
        entities = dict(entities)
        domain_specific = entities.get("domain_specific")
        if isinstance(domain_specific, dict):
            domain_specific = dict(domain_specific)
            # Compatibility with snapshots produced before timings moved to
            # parser_info. Timing values never describe document facts.
            domain_specific.pop("step_timings", None)
            entities["domain_specific"] = domain_specific
        payload["entities"] = entities
    return payload


def canonical_fact_fingerprint(result: Any) -> str:
    """Hash the canonical fact view with stable JSON ordering."""
    raw = json.dumps(
        canonical_fact_payload(result),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def canonical_fact_diff(
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, tuple[Any, Any]]:
    """Return deterministic leaf changes between two canonical fact views.

    The paths use the same dotted/list-index notation as mutation audit
    records, for example ``pages[0].tables[1].headers``.  A collection length
    change is reported at the collection path; equal-length collections are
    compared recursively so a middleware cannot hide a field change behind a
    broad snapshot fingerprint.
    """

    changes: dict[str, tuple[Any, Any]] = {}

    def _walk(left: Any, right: Any, path: str) -> None:
        if type(left) is not type(right):
            changes[path] = (left, right)
            return
        if isinstance(left, dict):
            keys = sorted(set(left) | set(right), key=str)
            for key in keys:
                child = f"{path}.{key}" if path else str(key)
                if key not in left:
                    changes[child] = (None, right[key])
                elif key not in right:
                    changes[child] = (left[key], None)
                else:
                    _walk(left[key], right[key], child)
            return
        if isinstance(left, list):
            if len(left) != len(right):
                changes[path] = (left, right)
                return
            for index, (left_item, right_item) in enumerate(zip(left, right)):
                _walk(left_item, right_item, f"{path}[{index}]")
            return
        if left != right:
            changes[path] = (left, right)

    _walk(before, after, "")
    return {path: changes[path] for path in sorted(changes)}


__all__ = [
    "canonical_fact_diff",
    "canonical_fact_fingerprint",
    "canonical_fact_payload",
]
