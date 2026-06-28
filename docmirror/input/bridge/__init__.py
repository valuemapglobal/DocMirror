# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Bridge package — converts internal extraction models to public ParseResult.

Purpose: Package marker for the BaseResult → ParseResult translation layer.

Main components: Re-exports from ``parse_result_bridge`` (when used).

Upstream: ``physical.models`` (``BaseResult``).

Downstream: ``entry.factory``, API output, plugins.
"""

from docmirror.input.bridge.parse_result_bridge import ParseResultBridge

__all__ = ["ParseResultBridge"]
