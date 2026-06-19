# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
KV identity enrichment parser for bank statement header rows.

Scans table header and preamble rows for embedded ``key: value`` cells (account
holder, account number, query period) and merges them into identity field maps.

Pipeline role: auxiliary parser in ``style_registry`` chain; runs before or alongside
grid parsers to populate identity metadata missing from Mirror entities.

Key exports: ``PARSER_ID``, ``enrich_identity_fields``.

Dependencies: ``bank_statement.context.StyleContext``.
"""

from __future__ import annotations

import re

from docmirror.plugins.bank_statement.context import StyleContext

PARSER_ID = "kv_identity"
_KV_IN_CELL_RE = re.compile(r"^([^:：]+)[:：]\s*(.+)$")


def enrich_identity_fields(
    ctx: StyleContext,
    identity_fields: dict[str, dict],
    identity_config: tuple[tuple[str, tuple[str, ...]], ...],
) -> dict[str, dict]:
    fields = dict(identity_fields)
    parse_result = ctx.parse_result
    if not parse_result or not hasattr(parse_result, "pages"):
        return fields

    for page in getattr(parse_result, "pages", []):
        for table in getattr(page, "tables", []):
            for row in getattr(table, "rows", []):
                for cell in getattr(row, "cells", []):
                    text = getattr(cell, "text", "").strip()
                    if not text:
                        continue
                    kv = _KV_IN_CELL_RE.match(text)
                    if not kv:
                        continue
                    key, val = kv.group(1).strip(), kv.group(2).strip()
                    for field_name, candidate_keys in identity_config:
                        if field_name in fields:
                            continue
                        for ck in candidate_keys:
                            if ck in key:
                                fields[field_name] = {
                                    "raw_name": key,
                                    "raw_value": val,
                                    "normalized_value": val,
                                    "data_type": "string",
                                }
                                break

    if "银座银行" in ctx.full_text and "bank_name" not in fields:
        fields["bank_name"] = {
            "raw_name": "银行名称",
            "raw_value": "银座银行",
            "normalized_value": "银座银行",
            "data_type": "string",
        }

    return fields
