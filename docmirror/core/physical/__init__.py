# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Physical layer package — immutable extraction data models.

Purpose: Namespace for the physical document representation (blocks, spans,
page layouts) produced during extraction.

Main components: Models from ``physical.models``.

Upstream: Extraction and segment modules.

Downstream: ``bridge.parse_result_bridge``, ``output`` exporters.
"""

from docmirror.core.physical.models import *  # noqa: F403
