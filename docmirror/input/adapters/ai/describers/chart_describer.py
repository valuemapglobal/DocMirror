# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Chart AI Description for Images (GA1.0-ODL-07 §P2)
=====================================================

Generates natural language descriptions of charts, figures, and images
using AI vision backends. Fills the ``alt_text`` field in DMIR image
blocks for PDF/UA accessibility and RAG context enrichment.

Usage::

    from docmirror.input.adapters.ai.describers.chart_describer import describe_chart_or_image

    alt_text = await describe_chart_or_image(
        image_bytes,
        context="chart",
        ai_backend=my_backend,
    )
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from docmirror.input.adapters.ai import get_ai_backend

if TYPE_CHECKING:
    from docmirror.input.adapters.ai.protocol import AIBackend

logger = logging.getLogger(__name__)


# ── Public API ───────────────────────────────────────────────────────────


async def describe_chart_or_image(
    image_bytes: bytes,
    *,
    context: str = "",
    ai_backend: AIBackend | None = None,
    options: dict[str, Any] | None = None,
) -> str:
    """Generate a description of a chart or image for accessibility.

    Args:
        image_bytes: PNG or JPEG bytes of the image/chart.
        context: Context hint (``"chart"``, ``"diagram"``, ``"photo"``, ``"table_screenshot"``).
        ai_backend: Optional pre-initialized AI backend. If ``None``, uses the
            default backend from environment config.
        options: Optional overrides passed to the AI backend.

    Returns:
        Natural language description, or empty string if no backend is available.

    Raises:
        RuntimeError: If the AI backend is explicitly needed but unavailable.
    """
    backend = ai_backend or get_ai_backend()

    if backend is None:
        logger.debug("No AI backend available for chart description. Skipping.")
        return ""

    if not backend.is_available:
        logger.warning(
            "AI backend '%s' is not available (check API key). Skipping chart description.",
            backend.name,
        )
        return ""

    try:
        description = await backend.describe_image(
            image_bytes,
            context=context,
            options=options,
        )
        logger.debug(
            "Chart description generated via %s (context=%s, %d chars)",
            backend.name, context, len(description),
        )
        return description
    except Exception as exc:
        logger.error(
            "Chart description failed via %s: %s",
            backend.name, exc,
        )
        return ""


async def describe_all_images(
    images: list[dict[str, Any]],
    *,
    ai_backend: AIBackend | None = None,
    options: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Generate descriptions for multiple images in batch.

    Args:
        images: List of image dicts, each with ``image_id``, ``bytes``,
            and optional ``context`` keys.
        ai_backend: Optional pre-initialized AI backend.
        options: Optional overrides passed to the AI backend.

    Returns:
        Dict mapping ``image_id`` to description string. Images that failed
        or had no backend available will have empty description strings.
    """
    descriptions: dict[str, str] = {}

    for img in images:
        img_id = img.get("image_id", "")
        img_bytes = img.get("bytes", b"")
        context = img.get("context", "")

        if not img_bytes:
            continue

        desc = await describe_chart_or_image(
            img_bytes,
            context=context,
            ai_backend=ai_backend,
            options=options,
        )
        descriptions[img_id] = desc

    return descriptions


# ── DMIR enrichment helper ────────────────────────────────────────────────


async def enrich_dmir_with_alt_text(
    dmir_dict: dict[str, Any],
    *,
    ai_backend: AIBackend | None = None,
    image_store: dict[str, bytes] | None = None,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Enrich a DMIR dict with AI-generated alt_text for image blocks.

    Modifies the DMIR dict in-place by filling ``alt_text`` fields
    in image blocks where they are empty or missing.

    Args:
        dmir_dict: The DMIR serialized dict (from ``serialize_dmir()``).
        ai_backend: Optional pre-initialized AI backend.
        image_store: Dict mapping image_id to image bytes (from the parse result).
        options: Optional overrides passed to the AI backend.

    Returns:
        The modified DMIR dict (same object, modified in-place).
    """
    backend = ai_backend or get_ai_backend()
    if backend is None or not backend.is_available:
        logger.debug("No AI backend available for DMIR alt-text enrichment.")
        return dmir_dict

    for page in dmir_dict.get("document", {}).get("pages", []):
        for image_block in page.get("images", []):
            if image_block.get("alt_text"):
                continue  # Already has alt text

            img_id = image_block.get("image_id", "")
            img_bytes = None
            if image_store and img_id in image_store:
                img_bytes = image_store[img_id]
            elif image_block.get("bytes"):
                img_bytes = image_block["bytes"]

            if not img_bytes:
                continue

            try:
                alt_text = await describe_chart_or_image(
                    img_bytes,
                    context="photo",  # Conservative default
                    ai_backend=backend,
                    options=options,
                )
                if alt_text:
                    image_block["alt_text"] = alt_text
                    image_block["alt_text_source"] = f"ai:{backend.name}"
            except Exception as exc:
                logger.warning(
                    "Failed to generate alt_text for image %s: %s",
                    img_id, exc,
                )

    return dmir_dict


__all__ = [
    "describe_chart_or_image",
    "describe_all_images",
    "enrich_dmir_with_alt_text",
]
