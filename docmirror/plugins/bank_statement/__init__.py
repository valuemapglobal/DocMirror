# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Bank statement style-family parsing (Community domain logic)."""

from docmirror.plugins.bank_statement.canonical import StyleMeta, build_style_meta
from docmirror.plugins.bank_statement.context import StyleContext, build_style_context
from docmirror.plugins.bank_statement.community_plugin import (
    BankStatementCommunityPlugin,
    plugin,
)
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
