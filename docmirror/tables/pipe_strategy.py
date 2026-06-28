# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Pipe strategy — delimiter-separated table extraction.

Purpose: Parses pipe- or tab-delimited text rows and merges continuation
lines for lightly structured digital exports.

Main components: ``_extract_by_pipe_delimited`` (delegates to SDU).

Upstream: Digital text zones with delimiter patterns.

Downstream: ``extract.engine`` as a fast tier.
"""

from __future__ import annotations

from docmirror.tables.structure_detect.pipe_page_extract import extract_pipe_delimited_table


def _extract_by_pipe_delimited(page_plum) -> list[list[str]] | None:
    """Pipe-delimited table extraction (Layer 0.5) — delegates to SDU."""
    return extract_pipe_delimited_table(page_plum)
