# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Page pipeline stages — discrete steps in per-page extraction.

Purpose: Package marker for prepare, segment, assemble, and finalize stage
runners invoked by ``PagePipeline``.

Main components: ``run_prepare``, ``run_segment``, ``run_assemble_zones``,
``run_finalize``.

Upstream: ``PagePipeline.run``.

Downstream: ``pipeline.handlers``, ``segment``, ``extract``, ``ocr``.
"""

from docmirror.core.pipeline.stages.page_prepare import run_prepare
from docmirror.core.pipeline.stages.page_segment import run_segment
from docmirror.core.pipeline.stages.page_assemble import run_assemble_zones

__all__ = ["run_prepare", "run_segment", "run_assemble_zones"]
