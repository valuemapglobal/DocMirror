# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Credit report community domain package.

Re-exports the registered ``CreditReportPlugin`` singleton for personal credit
report documents (征信报告).

Pipeline role: premium KV plugin; post-extract ``credit_report_sections`` hook may
further populate Mirror sections after extract.

Key exports: ``CreditReportPlugin``, ``plugin``.
"""

from docmirror.plugins.credit_report.community_plugin import CreditReportPlugin, plugin

__all__ = ["CreditReportPlugin", "plugin"]
