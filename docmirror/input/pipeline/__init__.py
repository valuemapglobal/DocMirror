"""Unified document entry pipeline.

The public parser path keeps ``ParseResult`` as the request-scoped SSOT and
builds MirrorJson vNext as its canonical projection. ``PerceiveResult.mirror``
therefore satisfies the vNext contract while ``PerceiveResult.parse_result``
keeps CLI, edition outputs, SDKs, and plugins on the richer parse object.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from docmirror.input.entry.perceive_result import PerceiveResult

logger = logging.getLogger(__name__)


async def perceive_document(path: str | Path, options: Any = None) -> PerceiveResult:
    """Parse a document and return a vNext mirror envelope plus ParseResult SSOT."""
    path = Path(path)
    try:
        from docmirror.input.entry.factory import PerceptionFactory
        from docmirror.models.mirror.core import MirrorCoreVNext

        control = options.normalized_control() if hasattr(options, "normalized_control") else None
        dispatcher = PerceptionFactory.get_dispatcher()
        parse_result = await dispatcher.process(
            path,
            skip_cache=getattr(options, "skip_cache", False),
            document_type=getattr(control.doc_type_hint, "value", None) if control else None,
            parse_control=control,
            max_pages=getattr(getattr(control, "pages", None), "max_pages", None) if control else None,
            enhance_mode=getattr(options, "enhance_mode", "standard"),
            on_progress=getattr(options, "on_progress", None),
        )

        opts = _mirror_options(path, options)
        mirror = MirrorCoreVNext().process(parse_result, opts).mirror
        return PerceiveResult(mirror=mirror, parse_result=parse_result)
    except Exception as exc:
        logger.exception("[Pipeline] UDTR path failed: %s", exc)
        return PerceiveResult(mirror=_failed_mirror(path, exc))


def _mirror_options(path: Path, options: Any) -> Any:
    from docmirror.models.mirror.core import MirrorOptions

    profile = getattr(options, "profile", None)
    engine_version = getattr(options, "engine_version", None)
    control = getattr(options, "control", None)
    output = getattr(control, "output", None)
    if profile is None:
        profile = getattr(output, "mirror_profile", None) or "canonical_full"
    if engine_version is None:
        engine_version = "0.1.0"
    return MirrorOptions(
        profile=str(profile),
        engine_version=str(engine_version),
        source_filename=str(path),
    )


def _failed_mirror(path: Path, exc: Exception) -> Any:
    from docmirror.models.mirror.vnext import (
        AssetStore,
        DiagnosticsInfo,
        DocumentInfo,
        EvidenceStore,
        GraphInfo,
        MirrorInfo,
        MirrorJsonVNext,
        OverallQuality,
        QualityInfo,
        SemanticsInfo,
        SourceInfo,
    )

    return MirrorJsonVNext(
        mirror=MirrorInfo(
            schema="docmirror.mirror_json",
            schema_version="3.0.0",
            engine="docmirror",
            engine_version="0.1.0",
            profile="canonical_full",
        ),
        source=SourceInfo(
            source_id="src:0001",
            filename=str(path),
            input_kind="failed",
            page_count=0,
        ),
        document=DocumentInfo(title={"text": path.name}),
        pages=[],
        evidence=EvidenceStore(),
        regions=[],
        blocks=[],
        graph=GraphInfo(nodes=[], edges=[]),
        semantics=SemanticsInfo(entities=[], facts=[], views={}),
        quality=QualityInfo(
            overall=OverallQuality(score=0.0, status="fail", confidence=0.0),
            gates=[
                {
                    "id": "gate:udtr_pipeline",
                    "status": "fail",
                    "message": str(exc),
                }
            ],
        ),
        diagnostics=DiagnosticsInfo(
            pipeline=[
                {
                    "stage": "input.pipeline",
                    "status": "error",
                    "message": str(exc),
                    "error_type": type(exc).__name__,
                }
            ],
            decisions=[],
            warnings=[],
            errors=[
                {
                    "stage": "input.pipeline",
                    "message": str(exc),
                    "error_type": type(exc).__name__,
                }
            ],
        ),
        assets=AssetStore(),
    )


__all__ = ["perceive_document"]
