# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Post-extract hook: rebuild bank ledger table from plugin transactions."""

from __future__ import annotations

import logging
from typing import Any

from docmirror.models.entities.parse_result import ParseResult
from docmirror.plugins.post_extract.base import PostExtractHook

logger = logging.getLogger(__name__)


class MirrorTableRebuildHook(PostExtractHook):
    hook_id = "mirror_table_rebuild"

    def apply(
        self,
        result: ParseResult,
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

        rebuild_fn = None
        for mod_path in (
            "docmirror_enterprise.plugins.bank_statement.table_rebuild",
            "docmirror.plugins.bank_statement.table_rebuild",
        ):
            try:
                mod = __import__(mod_path, fromlist=["rebuild_bank_table_from_transactions"])
                rebuild_fn = mod.rebuild_bank_table_from_transactions
                break
            except ImportError:
                continue
        if rebuild_fn is None:
            return

        if rebuild_fn(result, transactions):
            logger.info(
                "[PostExtract] Rebuilt bank ledger table from %d transactions",
                len(transactions),
            )
            try:
                from docmirror.core.extraction.provenance_stamps import stamp_mirror_block_provenance

                stamp_mirror_block_provenance(result)
            except Exception:
                pass
