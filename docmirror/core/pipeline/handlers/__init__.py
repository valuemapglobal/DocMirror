# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Pipeline handlers — zone-type-specific extraction dispatchers.

Purpose: Collection of handler functions invoked by ``page_assemble`` for
each semantic zone type on a page.

Main components: ``handle_text_zone``, ``handle_data_table_zone``,
``handle_formula_zone``, ``extract_scanned_page``.

Upstream: ``pipeline.stages.page_assemble``.

Downstream: ``extract``, ``ocr``, ``segment`` utilities.
"""
