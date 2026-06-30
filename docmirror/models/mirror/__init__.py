# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Mirror vNext access helpers."""

from docmirror.models.mirror.domain_access import (
    local_structure_evidence_pages_from_domain_specific,
)
from docmirror.models.mirror.page_access import (
    field_grid_structures_from_document,
    find_region_by_id,
    get_page_projection,
    iter_all_regions,
    iter_page_regions,
    micro_grid_structures_from_document,
    page_flow_texts,
    region_structure,
)
from docmirror.models.mirror.vnext_access import (
    get_page,
    iter_blocks,
    iter_evidence,
    iter_regions,
    iter_structures,
    resolve_ref,
)

__all__ = [
    "field_grid_structures_from_document",
    "find_region_by_id",
    "get_page_projection",
    "get_page",
    "iter_blocks",
    "iter_evidence",
    "iter_all_regions",
    "iter_regions",
    "iter_page_regions",
    "iter_structures",
    "local_structure_evidence_pages_from_domain_specific",
    "micro_grid_structures_from_document",
    "page_flow_texts",
    "region_structure",
    "resolve_ref",
]
