# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Document type resolver — fuses candidates into final document type.

Purpose: Aggregates weighted candidate scores and selects the best document
type label for profile and scene routing.

Main components: ``DocumentTypeResolver``.

Upstream: ``document_type_candidates`` collectors.

Downstream: ``scene.scene_resolver``, ``profile.resolver``.
"""

from __future__ import annotations

from docmirror.structure.resolution.base import BaseResolver, ResolverDecision
from docmirror.models.entities.hypothesis import ParseHypothesis


class DocumentTypeResolver(BaseResolver):
    """Resolve document type from multiple plugin/document-type candidates."""

    def resolve(
        self,
        candidates: list[ParseHypothesis],
    ) -> tuple[str, list[ResolverDecision]]:
        if not candidates:
            return "unknown", []

        def _score(c: ParseHypothesis) -> dict[str, float]:
            return {
                "evidence_coverage": min(1.0, len(c.evidence_ids) / 3.0) if c.evidence_ids else 0.3,
                "structure_consistency": c.confidence,
                "semantic_plausibility": c.confidence,
                "domain_fit": c.confidence,
                "preservation_score": 1.0,
                "conflict_penalty": len(c.conflicts_with) * 0.2,
            }

        ranked, decisions = self.rank(candidates, _score)
        doc_type = ranked[0].payload.get("document_type", "unknown") if ranked else "unknown"
        return doc_type, decisions
