# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
WeChat payment community domain package.

Re-exports the registered ``WeChatPaymentPlugin`` singleton and its column/keyword
configuration constants for tests and downstream imports.

Pipeline role: Community projector registered in the shared Post-Seal
``PluginRegistry`` for ``cashflow_payment`` table documents.

Key exports: ``WeChatPaymentPlugin``, ``plugin``, ``WECHAT_*`` config constants.
"""

from docmirror.plugins.wechat_payment.community_plugin import (
    WECHAT_COLUMN_REGISTRY,
    WECHAT_DEFAULT_COLUMNS,
    WECHAT_IDENTITY_FIELDS,
    WECHAT_SCENE_KEYWORDS,
    WECHAT_STANDARD_FIELDS,
    WeChatPaymentPlugin,
    plugin,
)

__all__ = [
    "WECHAT_COLUMN_REGISTRY",
    "WECHAT_DEFAULT_COLUMNS",
    "WECHAT_IDENTITY_FIELDS",
    "WECHAT_SCENE_KEYWORDS",
    "WECHAT_STANDARD_FIELDS",
    "WeChatPaymentPlugin",
    "plugin",
]
