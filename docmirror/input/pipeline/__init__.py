"""Unified document entry pipeline.

The public parser path returns the request-scoped ``ParseResult`` SSOT.
Canonical Mirror JSON and edition payloads are projections built later by the
output layer, so parsing has one result type and no mirror/parse wrapper.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from docmirror.models.entities.parse_result import ParseResult

logger = logging.getLogger(__name__)


async def perceive_document(path: str | Path, options: Any = None) -> ParseResult:
    """Parse a document and return the canonical runtime ``ParseResult``."""
    path = Path(path)
    try:
        from docmirror.input.entry.factory import PerceptionFactory

        control = options.normalized_control() if hasattr(options, "normalized_control") else None
        dispatcher = PerceptionFactory.get_dispatcher()
        return await dispatcher.process(
            path,
            skip_cache=getattr(options, "skip_cache", False),
            document_type=getattr(control.doc_type_hint, "value", None) if control else None,
            parse_control=control,
            max_pages=getattr(getattr(control, "pages", None), "max_pages", None) if control else None,
            enhance_mode=getattr(options, "enhance_mode", "standard"),
            on_progress=getattr(options, "on_progress", None),
        )
    except Exception as exc:
        logger.exception("[Pipeline] UDTR path failed: %s", exc)
        from docmirror.models.errors import build_failure_result

        return build_failure_result(
            "ORCHESTRATION_FAILURE",
            str(exc),
            file_path=str(path),
            file_type=path.suffix.lstrip(".").lower(),
        )


__all__ = ["perceive_document"]
