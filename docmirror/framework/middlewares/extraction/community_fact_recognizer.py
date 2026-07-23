# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Canonical domain recognition through the ``FactPatch`` mutation boundary."""

from __future__ import annotations

from docmirror.models.entities.parse_result import ParseResult

from ..base import BaseMiddleware


class CommunityFactRecognizer(BaseMiddleware):
    """Run installed Community recognition as part of the fact pipeline."""

    DEPENDS_ON = ["EvidenceEngine"]
    PROVIDES = ["domain_entities", "domain_records", "sections"]

    def process(self, result: ParseResult) -> ParseResult:
        from docmirror.input.canonical.fact_patch import apply_fact_patch
        from docmirror.plugins._runtime.runner import run_fact_recognition_sync

        before = result.fact_fingerprint()
        patch = run_fact_recognition_sync(
            result,
            full_text=result.full_text or result.raw_text,
        )
        result = apply_fact_patch(result, patch)
        after = result.fact_fingerprint()
        # Every applied field is audited by ``apply_fact_patch``. This summary
        # mutation makes the stage boundary explicit without replacing details.
        if after != before:
            result.record_mutation(
                self.name,
                target_block_id="parse_result",
                field_changed="fact_patch",
                old_value=before,
                new_value=after,
                confidence=patch.confidence,
                reason=f"applied FactPatch from {patch.provider_id}",
            )
        return result


__all__ = ["CommunityFactRecognizer"]
