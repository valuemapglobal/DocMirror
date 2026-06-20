# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
VAT invoice community domain plugin.

Premium community plugin for Chinese VAT invoices (key-value archetype). Declares
identity field label specs, builds minimal DEC via ``build_domain_data``, and
implements ``extract_from_mirror`` with ``extract_kv_community_output`` plus VAT-specific
OCR field normalization.

Pipeline role: one of six premium plugins; ``runner`` prefers ``extract_from_mirror``
when it returns records/fields, otherwise falls back to ``build_domain_data``.

Key exports: ``VATInvoicePlugin``, ``plugin``.

Dependencies: ``DomainPlugin``, ``dec_builder``, ``kv_community_extract``,
``kv_community_enrich.enrich_vat_invoice_output``.
"""

from __future__ import annotations

from collections.abc import Sequence

from docmirror.plugins import DomainPlugin


class VATInvoicePlugin(DomainPlugin):
    """Community edition plugin for VAT invoice document processing."""

    @property
    def domain_name(self) -> str:
        return "vat_invoice"

    @property
    def display_name(self) -> str:
        return "VAT Invoice (Community)"

    @property
    def edition(self) -> str:
        return "community"

    @property
    def identity_fields(self) -> Sequence[tuple[str, Sequence[str]]]:
        return (
            ("invoice_number", ("发票号码", "Invoice No", "发票号")),
            ("invoice_code", ("发票代码", "Invoice Code")),
            ("seller_name", ("销售方名称", "卖方名称", "Seller")),
            ("buyer_name", ("购买方名称", "买方名称", "Buyer")),
            ("total_amount", ("价税合计", "Total", "金额")),
            ("invoice_date", ("开票日期", "Date", "日期")),
        )

    def build_domain_data(self, _metadata, entities):
        from docmirror.plugins._base.dec_builder import build_dec_kv

        return build_dec_kv(
            "vat_invoice",
            {
                "invoice_number": entities.get("invoice_number", ""),
                "invoice_code": entities.get("invoice_code", ""),
                "seller_name": entities.get("seller_name", ""),
                "buyer_name": entities.get("buyer_name", ""),
                "total_amount": entities.get("total_amount", ""),
            },
        )

    def extract_from_mirror(self, parse_result, text: str = ""):
        from docmirror.plugins._base.kv_community_enrich import enrich_vat_invoice_output
        from docmirror.plugins._base.kv_community_extract import extract_kv_community_output

        out = extract_kv_community_output(
            self,
            parse_result,
            identity_specs=self.identity_fields,
            full_text=text,
        )
        return enrich_vat_invoice_output(out)


plugin = VATInvoicePlugin()
