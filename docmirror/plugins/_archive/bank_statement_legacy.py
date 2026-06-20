# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Archived bank statement domain plugin (pre style-family refactor).

Legacy built-in plugin with scene keywords, identity fields, and
``build_domain_data`` for bank statements. Superseded by
``bank_statement.community_plugin`` with StyleDetector → Registry pipeline.

Pipeline role: none — not discovered by ``plugin_registry``; retained for migration reference.

Key exports: ``BankStatementPlugin``, ``plugin`` (if present).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from docmirror.plugins import DomainPlugin


class BankStatementPlugin(DomainPlugin):
    """Built-in plugin for bank statement document processing."""

    @property
    def domain_name(self) -> str:
        return "bank_statement"

    @property
    def display_name(self) -> str:
        return "Bank Statement"

    @property
    def scene_keywords(self) -> Sequence[str]:
        return (
            "bank statement",
            "account statement",
            "transaction history",
            "statement of account",
            # Chinese
            "银行流水",
            "交易明细",
            "对账单",
            "账户流水",
        )

    @property
    def identity_fields(self) -> Sequence[tuple[str, Sequence[str]]]:
        return (
            ("account_holder", ("Account holder", "Account name", "Card holder", "Customer name")),
            ("account_number", ("Account number", "Card number", "Customer account number")),
            ("bank_name", ("Bank name", "Bank branch", "bank_name")),
            ("query_period", ("Query period", "From/to date", "Period")),
            ("currency", ("Currency",)),
            ("print_date", ("Print date",)),
        )

    def build_domain_data(
        self,
        metadata: dict[str, Any],
        entities: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Build DEC KV payload from extracted metadata and entities."""
        from docmirror.plugins._base.dec_builder import build_dec_kv

        return build_dec_kv(
            "bank_statement",
            {
                "account_holder": str(metadata.get("Account holder", entities.get("account_holder", ""))),
                "account_number": str(metadata.get("Account number", entities.get("account_number", ""))),
                "bank_name": str(entities.get("bank_name", "")),
                "query_period": str(metadata.get("Query period", entities.get("query_period", ""))),
                "currency": str(metadata.get("Currency", entities.get("currency", "CNY")) or "CNY"),
            },
        )

    def get_middleware_config(self) -> dict[str, Any]:
        return {
            "institution_detector_enabled": True,
            "amount_splitter_enabled": True,
        }


# Auto-discovery convention: module-level `plugin` instance
plugin = BankStatementPlugin()
