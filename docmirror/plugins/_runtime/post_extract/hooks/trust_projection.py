# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Post-extract hook: normalize plugin trust scores on edition JSON.

Ensures ``quality`` / ``validation`` blocks on the extracted edition payload carry
trust metrics from the plugin. Does **not** write back to ``ParseResult.trust``
(Architecture A — Core Mirror stays plugin-free).

Key exports: ``PluginTrustProjectionHook``.
"""

from __future__ import annotations

import logging
from typing import Any

from docmirror.models.entities.parse_result import ParseResult
from docmirror.plugins._runtime.post_extract.base import PostExtractHook

logger = logging.getLogger(__name__)


class PluginTrustProjectionHook(PostExtractHook):
    hook_id = "plugin_trust_projection"

    def apply(
        self,
        _result: ParseResult,
        *,
        extracted: dict[str, Any],
        edition: str,
        _document_type: str,
        _plugin: Any | None = None,
    ) -> None:
        quality = extracted.get("quality") or extracted.get("validation") or {}
        trust_score = quality.get("trust_score")
        if not trust_score:
            return
        try:
            out_quality = extracted.setdefault("quality", {})
            out_quality.setdefault("trust_score", float(trust_score))
            if quality.get("field_coverage") is not None:
                out_quality.setdefault("field_coverage", quality.get("field_coverage"))
            if quality.get("validation_score") is not None:
                out_quality.setdefault("validation_score", quality.get("validation_score"))
            if "validation_passed" in quality:
                out_quality.setdefault("validation_passed", quality.get("validation_passed"))
            if quality.get("confidence") is not None:
                out_quality.setdefault("confidence", quality.get("confidence"))
            out_quality.setdefault("source", f"post_extract:plugin:{edition}")

            enrichment = extracted.setdefault("enrichment", {})
            enrichment["trust_projection"] = {
                "edition": edition,
                "trust_score": float(trust_score),
            }
        except Exception as exc:
            logger.debug("[PostExtract] trust projection skip: %s", exc)
