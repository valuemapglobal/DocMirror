# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
BaseParser — Adapter Contract
===============================

First-principles design:

    1. ``to_parse_result()`` — pure extraction.  Each adapter controls its own
       parsing pipeline.  The result MUST have ``provenance`` already filled;
       ``perceive()`` no longer re-reads the file just to compute a hash.

    2. ``perceive()`` — extraction + middleware enrichment.  It calls
       ``to_parse_result()``, then runs the shared Orchestrator pipeline.
       It does NOT re-open the file.
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

    Adapters implement ``to_parse_result()`` and return a ParseResult with
    ``provenance`` already populated (file type, size, checksum).

    ``perceive()`` is the shared pipeline: extract → middleware enrichment.
    It never re-reads the input file.
    """

    @abstractmethod
    async def to_parse_result(self, file_path: Path, **kwargs) -> "ParseResult":
        """
        Extract the file into a ParseResult.

        The returned ParseResult SHOULD have ``provenance`` filled
        (at minimum ``file_type``).  Checksum and file size are best-effort.
        """
        ...

    async def perceive(self, file_path: Path, **context) -> "ParseResult":
        """
        Full pipeline: file → ParseResult → middleware → enhanced ParseResult.

        Pipeline:
            1. ``to_parse_result()`` — adapter-specific extraction
            2. Fill provenance if adapter forgot to
            3. ``Orchestrator.enhance()`` — middleware enrichment in-place

        Step 2 is a *safety net* — it avoids re-reading the full file by
        using a lightweight stat-only path if the adapter didn't fill provenance.
        """
        from docmirror.framework.orchestrator import Orchestrator

        pr = await self.to_parse_result(file_path)

        # ── Safety net: fill provenance if adapter didn't ──
        # We deliberately avoid a full SHA256 here (that was already done
        # in ParserDispatcher._validate).  A lightweight stat-only fallback
        # is sufficient for the safety-net case.
        if pr.provenance is None:
            from docmirror.models.entities.parse_result import ProvenanceInfo

            try:
                stat = file_path.stat()
                suffix = file_path.suffix.lstrip(".").lower()
                pr.provenance = ProvenanceInfo(
                    file_type=suffix,
                    file_size=stat.st_size,
                )
            except OSError:
                pass

        # ── Fill parser version if empty ──
        if not pr.parser_info.parser_version:
            import docmirror as _dm

            pr.parser_info.parser_version = getattr(_dm, "__version__", "0.4.0")

        # ── Middleware enrichment ──
        orchestrator = Orchestrator()
        file_type = (
            context.get("file_type")
            or (pr.provenance.file_type if pr.provenance else None)
            or "unknown"
        ).lower()
        enhance_mode = context.get("enhance_mode", "standard")

        return await orchestrator.enhance(
            pr,
            enhance_mode=enhance_mode,
            file_type=file_type,
        )
