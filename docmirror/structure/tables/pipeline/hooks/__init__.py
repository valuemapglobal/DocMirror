# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Table pipeline hooks — profile-specific post-normalization plugins.

Purpose: Package marker for domain hooks invoked by ``stage_domain`` (generic,
ledger borderless, etc.).

Main components: ``run_generic_hook``, ``run_ledger_borderless_hook``.

Upstream: ``table.pipeline.stage_domain`` hook resolution.

Downstream: Profile-specific table matrices.
"""

from docmirror.structure.tables.pipeline.hooks.generic import run_generic_hook
from docmirror.structure.tables.pipeline.hooks.ledger_borderless import run_ledger_borderless_hook

__all__ = ["run_generic_hook", "run_ledger_borderless_hook"]
