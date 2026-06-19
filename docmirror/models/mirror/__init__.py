# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Mirror PCM helpers."""

from docmirror.models.mirror.domain_access import (
    local_structure_evidence_pages_from_domain_specific,
)
from docmirror.models.mirror.legacy_access import (
    legacy_access_counts,
    log_legacy_access_summary,
    record_legacy_mirror_access,
    reset_legacy_access_counts,
)
from docmirror.models.mirror.page_access import (
    field_grid_structures_from_document,
    find_region_by_id,
    get_page_canvas,
    iter_all_regions,
    iter_page_regions,
    micro_grids_from_document,
    page_flow_texts,
    region_structure,
)

__all__ = [
    "field_grid_structures_from_document",
    "find_region_by_id",
    "get_page_canvas",
    "iter_all_regions",
    "iter_page_regions",
    "legacy_access_counts",
    "local_structure_evidence_pages_from_domain_specific",
    "log_legacy_access_summary",
    "micro_grids_from_document",
    "page_flow_texts",
    "record_legacy_mirror_access",
    "region_structure",
    "reset_legacy_access_counts",
]
