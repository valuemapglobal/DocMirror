# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Post-extract hook abstract base class.

Defines the contract for hooks that run after PEC extract completes. Implementations
receive the Mirror ``ParseResult``, the serialized ``extracted`` edition dict, edition
name, document type, and optional plugin reference.

Pipeline role: subclassed by modules under ``post_extract.hooks``; catalog loader
validates ``issubclass(..., PostExtractHook)`` before ``runner`` instantiates hooks.

Key exports: ``PostExtractHook``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from docmirror.models.entities.parse_result import ParseResult


class PostExtractHook(ABC):
    """Run after PEC extract; may mutate Mirror when ``mutates_mirror`` is set in catalog."""

    hook_id: str = ""

    @abstractmethod
    def apply(
        self,
        result: ParseResult,
        *,
        extracted: dict[str, Any],
        edition: str,
        document_type: str,
        plugin: Any | None = None,
    ) -> None:
        """Apply hook side effects."""
