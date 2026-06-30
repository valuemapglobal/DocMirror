# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Community plugin package.

Re-exports community configuration helpers from ``community_config`` for
public plugin API stability, and provides **explicit static imports** of all
community plugin modules — replacing the old ``importlib.import_module()``
discovery pattern.

Key exports: ``bank_statement_plugin``, ``vat_invoice_plugin``, ... (one
``DomainPlugin`` instance per domain), plus all ``community_config`` symbols
(``load_plugin_capability``, ``get_community_premium_domains``, ...).

Dependencies: ``community_config`` (discovery helpers), individual community
plugin modules (``bank_statement.community_plugin``, ...).
"""

from __future__ import annotations

# ---- Re-export community_config helpers for public plugin API stability ----
from docmirror.plugins._runtime.community_config import *  # noqa: F401,F403
from docmirror.plugins.alipay_payment.community_plugin import plugin as alipay_payment_plugin

# ---- Explicit static plugin imports (one per community domain) ----
# Each community plugin module exposes a ``plugin`` instance of DomainPlugin.
# Importing them here statically means any import error is raised eagerly at
# load time, not swallowed silently by a try/except in importlib.
from docmirror.plugins.bank_statement.community_plugin import plugin as bank_statement_plugin
from docmirror.plugins.business_license.community_plugin import plugin as business_license_plugin
from docmirror.plugins.credit_report.community_plugin import plugin as credit_report_plugin
from docmirror.plugins.generic.community_plugin import plugin as generic_plugin
from docmirror.plugins.vat_invoice.community_plugin import plugin as vat_invoice_plugin
from docmirror.plugins.wechat_payment.community_plugin import plugin as wechat_payment_plugin

__all__ = [  # noqa: F405 — re-exported names from community_config
    "bank_statement_plugin",
    "vat_invoice_plugin",
    "credit_report_plugin",
    "business_license_plugin",
    "alipay_payment_plugin",
    "wechat_payment_plugin",
    "generic_plugin",
]
