# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Post-extract hooks package — audited Mirror mutations after PEC extract.

Re-exports the hook ABC and the runner invoked from ``runner._finalize_extract``
once edition JSON is assembled.

Pipeline role: final stage of plugin extract; hooks may enrich ``ParseResult`` or
``extracted`` dict when configured in ``post_extract.yaml``.

Key exports: ``PostExtractHook``, ``run_post_extract_hooks``.
"""

from docmirror.plugins.post_extract.base import PostExtractHook
from docmirror.plugins.post_extract.runner import run_post_extract_hooks

__all__ = ["PostExtractHook", "run_post_extract_hooks"]
