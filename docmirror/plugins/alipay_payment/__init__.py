# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Alipay payment community domain logic."""

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
