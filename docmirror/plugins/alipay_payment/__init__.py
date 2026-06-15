# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Alipay payment community domain package.

Re-exports the registered ``AlipayPaymentPlugin`` singleton and column/identity
configuration for the Alipay transaction export document type.

Pipeline role: premium community plugin discovered by ``registry``; extract path
mirrors WeChat via ``BaseTableParser.extract_from_mirror``.

Key exports: ``AlipayPaymentPlugin``, ``plugin``, ``ALIPAY_*`` config constants.
"""

from docmirror.plugins.alipay_payment.community_plugin import (
    ALIPAY_COLUMN_REGISTRY,
    ALIPAY_IDENTITY_FIELDS,
    ALIPAY_STANDARD_FIELDS,
    AlipayPaymentPlugin,
    plugin,
)

__all__ = [
    "ALIPAY_COLUMN_REGISTRY",
    "ALIPAY_IDENTITY_FIELDS",
    "ALIPAY_STANDARD_FIELDS",
    "AlipayPaymentPlugin",
    "plugin",
]
