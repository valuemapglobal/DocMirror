# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Entity collector — gathers key-value entities from extracted blocks.

Purpose: Scans preamble KV blocks and inline patterns to populate structured
entity fields on the document result.

Main components: ``collect_kv_entities``.

Upstream: Extracted ``Block`` lists with ``key_value`` types.

Downstream: canonical ParseResult assembly and domain recognition.
"""

from __future__ import annotations

from docmirror.models.entities.domain import PageLayout


def collect_kv_entities(pages: list[PageLayout]) -> dict[str, str]:
    """
    Collect entities from extracted key_value blocks.

    Note: Full entity extraction (regex/bank name/account name/account number etc.)
    has been moved to middlewares.entity_extractor.EntityExtractor middleware.
    This method only performs simple KV block aggregation to ensure
    Canonical adapter metadata has basic entity information.
    """
    entities: dict[str, str] = {}
    for page in pages:
        for block in page.blocks:
            if block.block_type == "key_value" and isinstance(block.raw_content, dict):
                entities.update(block.raw_content)
    return entities
