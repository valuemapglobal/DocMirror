# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Post-extract hook executor — runs catalog-matched hooks after PEC extract.

Hooks enrich the edition ``extracted`` payload only. Core ``ParseResult`` used for
``001_mirror.json`` is snapshotted before plugins (Architecture A).

Pipeline role: called from ``runner._finalize_extract`` immediately before returning
edition JSON to the caller.

Key exports: ``run_post_extract_hooks``.

Dependencies: ``post_extract.catalog``, ``ParseResult.record_mutation``.
"""

from __future__ import annotations

import logging
from typing import Any

from docmirror.models.entities.parse_result import ParseResult
from docmirror.plugins._runtime.post_extract.catalog import get_hook_class, resolve_post_extract_hooks

logger = logging.getLogger(__name__)


def run_post_extract_hooks(
    result: ParseResult,
    *,
    extracted: dict[str, Any],
    edition: str,
    document_type: str,
    plugin: Any | None = None,
) -> None:
    """Run matching hooks; edition payload enrichment only."""
    for spec in resolve_post_extract_hooks(
        document_type=document_type,
        edition=edition,
        extracted=extracted,
    ):
        try:
            if spec.mutates_facts:
                logger.warning(
                    "[PostExtract] Hook %s declares mutates_facts=true; skipped because facts are sealed",
                    spec.hook_id,
                )
                continue
            hook_cls = get_hook_class(spec)
            hook = hook_cls()
            hook.hook_id = spec.hook_id
            projection_input = result.model_copy(deep=True)
            hook.apply(
                projection_input,
                extracted=extracted,
                edition=edition,
                document_type=document_type,
                plugin=plugin,
            )
            logger.debug("[PostExtract] Applied hook %s", spec.hook_id)
        except Exception as exc:
            logger.warning("[PostExtract] Hook %s failed: %s", spec.hook_id, exc)
