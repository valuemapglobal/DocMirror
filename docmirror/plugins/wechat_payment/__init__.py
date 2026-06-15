# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""WeChat payment community domain logic."""

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
