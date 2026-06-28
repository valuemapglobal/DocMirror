# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Post-extract hook: annotate bank ledger rebuild on edition JSON.

When enterprise bank-statement extract produces structured transactions, records
rebuild metadata on the edition ``enrichment`` block. Core ``ParseResult`` /
``001_mirror.json`` physical tables are preserved (Architecture A).

Key exports: ``MirrorTableRebuildHook``.
"""

from __future__ import annotations

import logging
from typing import Any

from docmirror.models.entities.parse_result import ParseResult
from docmirror.plugins._runtime.post_extract.base import PostExtractHook

logger = logging.getLogger(__name__)


class MirrorTableRebuildHook(PostExtractHook):
    hook_id = "mirror_table_rebuild"

    def apply(
        self,
        _result: ParseResult,
        *,
        extracted: dict[str, Any],
        edition: str,
        document_type: str,
        plugin: Any | None = None,
    ) -> None:
        if document_type != "bank_statement":
            return
        structured = extracted.get("structured_data") or extracted.get("extraction", {}).get("structured_data") or {}
        transactions = structured.get("transactions") or []
        if not transactions:
            extraction = extracted.get("extraction", {})
            transactions = extraction.get("records") or extracted.get("data", {}).get("records") or []
        if not transactions:
            return

        rebuild_available = False
        for mod_path in ("docmirror_enterprise.plugins.bank_statement.table_rebuild",):
            try:
                __import__(mod_path, fromlist=["rebuild_bank_table_from_transactions"])
                rebuild_available = True
                break
            except ImportError:
                continue

        enrichment = extracted.setdefault("enrichment", {})
        enrichment["bank_table_rebuild"] = {
            "edition": edition,
            "transaction_count": len(transactions),
            "rebuild_available": rebuild_available,
            "status": "edition_only",
            "note": "Core Mirror pages[].tables preserved; rebuild not written back to ParseResult",
        }
        logger.info(
            "[PostExtract] Recorded bank table rebuild metadata for %d transactions (edition-only)",
            len(transactions),
        )
