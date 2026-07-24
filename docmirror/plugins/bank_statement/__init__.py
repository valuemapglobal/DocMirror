# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Bank statement community domain package.

Public exports for the style-family parsing stack: style detection, parser registry,
canonical record builders, and the registered ``plugin`` singleton consumed by
``plugin_registry``.

Pipeline role: ``bank_statement.community_plugin`` is registered as a
Community projector in the shared Post-Seal ``PluginRegistry``; ``derive``
runs StyleDetector → parser registry → ``ProjectionData``.

Key exports: ``BankStatementCommunityPlugin``, ``BankStyleDetector``,
``BankStyleParserRegistry``, ``StyleContext``, ``StyleDetectionResult``,
``StyleMeta``, ``plugin``.
"""

from docmirror.plugins.bank_statement.canonical import StyleMeta, build_style_meta
from docmirror.plugins.bank_statement.community_plugin import (
    BankStatementCommunityPlugin,
    plugin,
)
from docmirror.plugins.bank_statement.context import StyleContext, build_style_context
from docmirror.plugins.bank_statement.style_detector import BankStyleDetector, StyleDetectionResult
from docmirror.plugins.bank_statement.style_registry import BankStyleParserRegistry

__all__ = [
    "BankStatementCommunityPlugin",
    "BankStyleDetector",
    "BankStyleParserRegistry",
    "StyleContext",
    "StyleDetectionResult",
    "StyleMeta",
    "build_style_context",
    "build_style_meta",
    "plugin",
]
