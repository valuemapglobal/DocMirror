# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Hidden Text Detector — Detect invisible/hidden text in document content.

Scans text blocks for:
- Zero opacity / near-zero opacity
- Rendering mode 3 (invisible text rendering)
- Near-zero font size

These are common techniques used to hide prompt injection payloads inside
PDFs and other document formats.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class HiddenTextFlag:
    """A single hidden text finding with location and reason."""

    block_id: str = ""
    content: str = ""
    reason: str = ""
    bbox: list[float] | None = None
    confidence: float = 1.0


class HiddenTextDetector:
    """Detect invisible/hidden text in parsed document text blocks.

    Checks three invisibility signals:
    - **Zero/near-zero opacity**: ``text_opacity < 0.01``
    - **Invisible rendering mode**: ``rendering_mode == 3`` (text is invisible)
    - **Near-zero font size**: ``font_size < 0.5``
    """

    MIN_OPACITY_THRESHOLD: float = 0.01
    MIN_FONT_SIZE_THRESHOLD: float = 0.5

    def detect(
        self, text_blocks: list[dict[str, Any]]
    ) -> list[HiddenTextFlag]:
        """Scan *text_blocks* for invisible/hidden content.

        Args:
            text_blocks: List of text block dicts. Each dict may contain
                ``block_id``, ``content``, ``text_opacity``,
                ``rendering_mode``, ``font_size``, and ``bbox`` keys.

        Returns:
            List of ``HiddenTextFlag`` for every block that appears hidden.
        """
        flags: list[HiddenTextFlag] = []
        for i, block in enumerate(text_blocks):
            block_id = block.get("block_id", str(i))
            content = block.get("content", "")
            if not content.strip():
                continue
            reason = self._check_invisible(block)
            if reason:
                flags.append(
                    HiddenTextFlag(
                        block_id=block_id,
                        content=content,
                        reason=reason,
                        bbox=block.get("bbox"),
                    )
                )
        return flags

    def sanitize(
        self, text_blocks: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Remove invisible text blocks from the list.

        Args:
            text_blocks: List of text block dicts.

        Returns:
            Filtered list with only visible blocks.
        """
        return [
            b for b in text_blocks if not self._check_invisible(b)
        ]

    def _check_invisible(self, block: dict[str, Any]) -> str | None:
        """Check if a text block is invisible.

        Returns:
            A reason string (``"zero_opacity"``,
            ``"invisible_rendering_mode"``, ``"zero_font_size"``) or
            ``None`` if the block appears visible.
        """
        # 1. Zero / near-zero opacity
        opacity = block.get("text_opacity", 1.0)
        if isinstance(opacity, (int, float)) and opacity < self.MIN_OPACITY_THRESHOLD:
            return "zero_opacity"

        # 2. Rendering mode 3 (invisible)
        rendering_mode = block.get("rendering_mode", 0)
        if rendering_mode == 3:
            return "invisible_rendering_mode"

        # 3. Near-zero font size
        font_size = block.get("font_size", 12.0)
        if (
            isinstance(font_size, (int, float))
            and font_size < self.MIN_FONT_SIZE_THRESHOLD
        ):
            return "zero_font_size"

        return None


__all__ = [
    "HiddenTextDetector",
    "HiddenTextFlag",
]
