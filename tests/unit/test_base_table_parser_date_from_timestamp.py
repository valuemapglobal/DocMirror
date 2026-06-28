# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Date derivation from timestamp for transaction-time ledgers (PSBC etc.)."""

from __future__ import annotations

from docmirror.plugins._base.column_registry import ColumnMapping
from docmirror.plugins.bank_statement.community_plugin import BankStatementCommunityPlugin


def test_normalize_derives_date_from_timestamp():
    plugin = BankStatementCommunityPlugin()
    out = plugin._normalize({"交易时间": "2024-06-01 12:30:00", "摘要": "test"})
    assert out.get("timestamp")
    assert out.get("date") == "2024-06-01"
