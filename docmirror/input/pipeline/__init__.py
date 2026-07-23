"""Unified document entry pipeline returning an immutable canonical snapshot."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from docmirror.models.sealed import SealedParseResult

logger = logging.getLogger(__name__)


async def perceive_document(path: str | Path, options: Any = None) -> SealedParseResult:
    """Parse a document and return the sealed canonical fact snapshot."""
    path = Path(path)
    try:
        from docmirror.input.acceptance import accept_source
        from docmirror.input.entry.factory import PerceptionFactory
        from docmirror.input.entry.options import normalize_parse_policy

        policy = options.normalized_policy() if hasattr(options, "normalized_policy") else normalize_parse_policy()
        source = accept_source(path)
        dispatcher = PerceptionFactory.get_dispatcher()
        try:
            return await dispatcher.process(
                source,
                policy,
                max_workers=getattr(options, "max_workers", None),
                on_progress=getattr(options, "on_progress", None),
            )
        finally:
            source.cleanup()
    except Exception as exc:
        from docmirror.input.models import InputRejectedError

        if isinstance(exc, InputRejectedError):
            from docmirror.models.errors import build_failure_result
            from docmirror.models.sealed import seal_parse_result

            return seal_parse_result(
                build_failure_result(
                    exc.code,
                    str(exc),
                    file_path=str(path),
                    file_type=path.suffix.lstrip(".").lower(),
                )
            )
        logger.exception("[Pipeline] UDTR path failed: %s", exc)
        from docmirror.models.errors import build_failure_result
        from docmirror.models.sealed import seal_parse_result

        return seal_parse_result(
            build_failure_result(
                "ORCHESTRATION_FAILURE",
                str(exc),
                file_path=str(path),
                file_type=path.suffix.lstrip(".").lower(),
            )
        )


__all__ = ["perceive_document"]
