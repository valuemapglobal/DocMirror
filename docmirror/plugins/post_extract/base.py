# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Post-Extract Hook base class."""

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
