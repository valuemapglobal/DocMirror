# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.

"""
Debug package — diagnostic artifacts and evidence crops for extraction runs.

Purpose: Optional debug outputs (JSON artifacts, field crops) when debug mode
is enabled during parsing.

Main components: ``debug.artifact``, ``debug.crop_generator``.

Upstream: ``ParseResult``, pipeline provenance stamps.

Downstream: Developer inspection, EHL annex builds.
"""

from docmirror.core.debug.artifact import build_debug_artifact, is_debug_mode, write_debug_artifact

__all__ = ["build_debug_artifact", "write_debug_artifact", "is_debug_mode"]
