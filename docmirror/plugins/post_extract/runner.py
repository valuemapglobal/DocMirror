# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Execute post-extract hooks after PEC extract."""

from __future__ import annotations

import logging
from typing import Any

from docmirror.models.entities.parse_result import ParseResult
from docmirror.plugins.post_extract.catalog import get_hook_class, resolve_post_extract_hooks

logger = logging.getLogger(__name__)


def run_post_extract_hooks(
    result: ParseResult,
    *,
    extracted: dict[str, Any],
    edition: str,
    document_type: str,
    plugin: Any | None = None,
) -> None:
    """Run matching hooks; mutations are recorded on ``result.mutations``."""
    for spec in resolve_post_extract_hooks(
        document_type=document_type,
        edition=edition,
        extracted=extracted,
    ):
        try:
            hook_cls = get_hook_class(spec)
            hook = hook_cls()
            hook.hook_id = spec.hook_id
            hook.apply(
                result,
                extracted=extracted,
                edition=edition,
                document_type=document_type,
                plugin=plugin,
            )
            if spec.mutates_mirror:
                result.record_mutation(
                    middleware_name=f"post_extract:{spec.hook_id}",
                    target_block_id=document_type,
                    field_changed=",".join(spec.provides) or spec.hook_id,
                    old_value=None,
                    new_value=True,
                    reason=f"post_extract hook {spec.hook_id}",
                )
            logger.debug("[PostExtract] Applied hook %s", spec.hook_id)
        except Exception as exc:
            logger.warning("[PostExtract] Hook %s failed: %s", spec.hook_id, exc)
