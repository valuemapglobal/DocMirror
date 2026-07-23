# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
BaseParser — Adapter Contract
===============================

First-principles design:

    1. ``to_parse_result()`` — adapter evidence/basic-fact extraction followed
       by canonical assembly. The result MUST have ``provenance`` already filled;
       ``perceive()`` no longer re-reads the file just to compute a hash.

    2. ``perceive()`` — extraction + middleware enrichment via the shared
       ``Orchestrator`` singleton (``docmirror.framework.di.get_orchestrator()``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path


class ParserStatus(str, Enum):
    """Parsing status enumeration."""

    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILURE = "failure"


class BaseParser(ABC):
    """
    Abstract base class for all document parsers.

    Adapters implement ``to_parse_result()`` by mapping source-specific evidence
    and basic facts into canonical assembly. The returned ParseResult has
    ``provenance`` already populated (file type, size, checksum).

    ``perceive()`` is the shared pipeline: extract → middleware enrichment.
    It never re-reads the input file.
    """

    @abstractmethod
    async def to_parse_result(self, file_path: Path, **kwargs) -> ParseResult:
        """
        Extract the file into a ParseResult.

        The returned ParseResult SHOULD have ``provenance`` filled
        (at minimum ``file_type``).  Checksum and file size are best-effort.
        """
        ...

    async def perceive(self, file_path: Path, **context) -> ParseResult:
        """
        Full pipeline: file → ParseResult → middleware → enhanced ParseResult.

        Pipeline:
            1. ``to_parse_result()`` — adapter-specific extraction
            2. Fill provenance if adapter forgot to
            3. ``Orchestrator.enhance()`` — middleware enrichment in-place

        Step 2 is a *safety net* — it avoids re-reading the full file by
        using a lightweight stat-only path if the adapter didn't fill provenance.
        """
        pr = await self.to_parse_result(file_path, **context)

        # ParsePolicy belongs to the canonical pipeline, not to individual
        # adapter implementations. Attach it centrally so registry backends,
        # fallbacks, and built-in adapters have identical force/prefer semantics.
        from docmirror.input.canonical import attach_parse_policy

        parse_policy = context.get("parse_policy")
        parse_policy_dict = context.get("parse_policy_dict")
        if parse_policy_dict is None and parse_policy is not None and hasattr(parse_policy, "to_dict"):
            parse_policy_dict = parse_policy.to_dict()
        attach_parse_policy(
            pr,
            doc_type_hint=context.get("doc_type_hint"),
            doc_type_hint_strength=context.get("doc_type_hint_strength"),
            parse_policy=parse_policy_dict,
            parse_policy_fingerprint=context.get("parse_policy_fingerprint"),
        )

        # ── Safety net: fill provenance if adapter didn't ──
        # We deliberately avoid a full SHA256 here (that was already done
        # by InputAcceptance).  A lightweight stat-only fallback
        # is sufficient for the safety-net case.
        if pr.provenance is None:
            from docmirror.models.entities.parse_result import ProvenanceInfo

            try:
                stat = file_path.stat()
                suffix = file_path.suffix.lstrip(".").lower()
                pr.provenance = ProvenanceInfo(
                    file_path=str(file_path),
                    file_type=context.get("file_type") or suffix,
                    file_size=int(context.get("file_size") or stat.st_size),
                    checksum=context.get("checksum", ""),
                    mime_type=context.get("mime_type", ""),
                    capability_id=context.get("capability_id", ""),
                    content_model=context.get("content_model", ""),
                )
            except OSError:
                pass
        else:
            pr.provenance.file_path = pr.provenance.file_path or str(file_path)
            pr.provenance.checksum = pr.provenance.checksum or context.get("checksum", "")
            pr.provenance.mime_type = pr.provenance.mime_type or context.get("mime_type", "")
            pr.provenance.capability_id = pr.provenance.capability_id or context.get("capability_id", "")
            pr.provenance.content_model = pr.provenance.content_model or context.get("content_model", "")
            if not pr.provenance.file_size and context.get("file_size"):
                pr.provenance.file_size = int(context.get("file_size") or 0)
        if pr.provenance is not None and context.get("source_file_path"):
            # Middleware must classify against caller-visible provenance, not the
            # private accepted snapshot name (for example ``source.pdf``).
            pr.provenance.file_path = str(context["source_file_path"])

        # ── Fill parser version if empty ──
        if not pr.parser_info.parser_version:
            import docmirror as _dm

            pr.parser_info.parser_version = getattr(_dm, "__version__", "unknown")

        # ── Middleware enrichment ──
        from docmirror.framework.di.container import get_orchestrator

        orchestrator = get_orchestrator()
        file_type = (
            context.get("file_type") or (pr.provenance.file_type if pr.provenance else None) or "unknown"
        ).lower()
        enhance_mode = context.get("enhance_mode", "standard")
        content_model = context.get("content_model", "")

        return await orchestrator.enhance(
            pr,
            enhance_mode=enhance_mode,
            file_type=file_type,
            content_model=content_model,
            on_progress=context.get("on_progress"),
        )
