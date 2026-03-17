"""
Entity Collection from Document Layouts
"""
from __future__ import annotations

from typing import Dict, List

from docmirror.models.domain import PageLayout


def collect_kv_entities(pages: List[PageLayout]) -> Dict[str, str]:
    """
    Collect entities from extracted key_value blocks.
    
    Note: Full entity extraction (regex/bank name/account name/account number etc.)
    has been moved to middlewares.entity_extractor.EntityExtractor middleware.
    This method only performs simple KV block aggregation to ensure
    BaseResult.metadata has basic entity information.
    """
    entities: Dict[str, str] = {}
    for page in pages:
        for block in page.blocks:
            if block.block_type == "key_value" and isinstance(block.raw_content, dict):
                entities.update(block.raw_content)
    return entities
