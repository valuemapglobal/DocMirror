# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Post-extract hook: project plugin quality trust scores onto Mirror."""

from __future__ import annotations

import logging
from typing import Any

from docmirror.models.entities.parse_result import ParseResult, TrustResult
from docmirror.plugins.post_extract.base import PostExtractHook

logger = logging.getLogger(__name__)


class PluginTrustProjectionHook(PostExtractHook):
    hook_id = "plugin_trust_projection"

    def apply(
        self,
        result: ParseResult,
        *,
        extracted: dict[str, Any],
        edition: str,
        document_type: str,
        plugin: Any | None = None,
    ) -> None:
        quality = extracted.get("quality") or extracted.get("validation") or {}
        trust_score = quality.get("trust_score")
        if not trust_score:
            return
        try:
            result.trust = TrustResult(
                trust_score=float(trust_score),
                validation_score=float(quality.get("field_coverage") or quality.get("validation_score") or 0),
                validation_passed=bool(quality.get("validation_passed", False)),
                details={"source": f"post_extract:plugin:{edition}"},
            )
            conf = quality.get("confidence")
            if conf and float(conf) > result.confidence:
                result.confidence = float(conf)
        except Exception as exc:
            logger.debug("[PostExtract] trust projection skip: %s", exc)
