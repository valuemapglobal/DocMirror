# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Canonical domain recognition.

Community plugins are recognizers here, not output projectors.  Their factual
discoveries are merged into ParseResult before validation and cache write, so
delivery selection can never decide whether those facts exist.
"""

from __future__ import annotations

from docmirror.models.entities.parse_result import ParseResult

from ..base import BaseMiddleware


class CommunityFactRecognizer(BaseMiddleware):
    """Run installed Community recognition as part of the fact pipeline."""

    DEPENDS_ON = ["EvidenceEngine", "InstitutionDetector"]
    PROVIDES = ["domain_entities", "domain_records", "sections"]

    def process(self, result: ParseResult) -> ParseResult:
        from docmirror.plugins._runtime.runner import run_plugin_extract_sync

        before = result.fact_fingerprint()
        run_plugin_extract_sync(
            result,
            edition="community",
            full_text=result.full_text or result.raw_text,
            file_path=result.file_path,
        )
        after = result.fact_fingerprint()
        if after != before:
            result.record_mutation(
                self.name,
                target_block_id="parse_result",
                field_changed="domain_facts",
                old_value=before,
                new_value=after,
                reason="canonical community domain recognition",
            )
        return result


__all__ = ["CommunityFactRecognizer"]
