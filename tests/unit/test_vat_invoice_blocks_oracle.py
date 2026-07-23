# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""VAT invoice S5 blocks + KV extract (Design 20 residual)."""

from __future__ import annotations

from docmirror.models.entities.parse_result import DocumentEntities, KeyValuePair, PageContent, ParseResult
from docmirror.models.mirror.block_fields import collect_kv_fields_from_blocks
from docmirror.models.sealed import seal_parse_result
from docmirror.output.mirror_projector import project_mirror
from docmirror.plugins._base.kv_community_extract import extract_kv_community_output
from docmirror.plugins.vat_invoice.community_plugin import VATInvoicePlugin


def test_vat_collects_kv_from_blocks():
    pr = ParseResult(
        pages=[
            PageContent(
                page_number=1,
                key_values=[
                    KeyValuePair(key="发票号码", value="12345678"),
                    KeyValuePair(key="价税合计", value="1000.00"),
                ],
            )
        ],
        entities=DocumentEntities(document_type="vat_invoice"),
    )
    fields = collect_kv_fields_from_blocks(project_mirror(seal_parse_result(pr), mirror_level="standard"))
    assert fields["发票号码"] == "12345678"
    assert fields["价税合计"] == "1000.00"

    plugin = VATInvoicePlugin()
    out = extract_kv_community_output(plugin, pr, identity_specs=plugin.identity_fields)
    data = out.get("data") or {}
    assert data.get("invoice_number") == "12345678" or "12345678" in str(data)


def test_vat_page_blocks_include_s5():
    pr = ParseResult(
        pages=[PageContent(page_number=1, key_values=[KeyValuePair(key="发票代码", value="ABC")])],
        entities=DocumentEntities(document_type="vat_invoice"),
    )
    api = project_mirror(seal_parse_result(pr), mirror_level="standard")
    blocks = api["pages"][0].get("blocks") or []
    assert any(block.get("morphology") == "S5" for block in blocks)
