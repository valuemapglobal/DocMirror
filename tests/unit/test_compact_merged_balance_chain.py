# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""compact_merged balance chain refinement safety."""

from __future__ import annotations

from docmirror.plugins.bank_statement.styles.compact_merged import refine_directions_from_balance_chain


def test_refine_directions_skips_unparseable_balance():
    records = [
        {
            "normalized": {
                "amount": 100.0,
                "balance": "2024-03-261200.00395.6713050110229700000024国任财产保险股",
                "direction": "other",
            }
        },
        {
            "normalized": {
                "amount": 50.0,
                "balance": 150.0,
                "direction": "other",
            }
        },
    ]
    refine_directions_from_balance_chain(records)
    assert records[1]["normalized"]["direction"] in ("other", "income", "expense")
