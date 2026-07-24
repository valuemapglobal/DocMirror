# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
VAT invoice community domain package.

Re-exports the registered ``VATInvoicePlugin`` singleton for VAT/special invoice
document processing in community edition.

Pipeline role: Community projector registered in the shared Post-Seal
``PluginRegistry``; derivation reads sealed OCR evidence without writing back.

Key exports: ``VATInvoicePlugin``, ``plugin``.
"""

from docmirror.plugins.vat_invoice.community_plugin import VATInvoicePlugin, plugin

__all__ = ["VATInvoicePlugin", "plugin"]
