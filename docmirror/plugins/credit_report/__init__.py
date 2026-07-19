# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Credit report community domain package.

Re-exports the registered ``CreditReportPlugin`` singleton for personal brief,
personal detail, and enterprise credit report documents (征信报告).

Pipeline role: premium KV plugin; post-extract ``credit_report_sections`` hook may
further populate Mirror sections after extract.

Key exports: ``CreditReportPlugin``, ``plugin``.
"""

from typing import Any

__all__ = [
    "CreditReportPlugin",
    "extract_credit_accounts_from_local_structure_evidence",
    "extract_credit_repayment_records",
    "plugin",
]


def __getattr__(name: str) -> Any:
    if name in {"CreditReportPlugin", "plugin"}:
        from docmirror.plugins.credit_report.community_plugin import CreditReportPlugin, plugin

        return {"CreditReportPlugin": CreditReportPlugin, "plugin": plugin}[name]
    if name == "extract_credit_repayment_records":
        from docmirror.plugins.credit_report.repayment_grid import extract_credit_repayment_records

        return extract_credit_repayment_records
    if name == "extract_credit_accounts_from_local_structure_evidence":
        from docmirror.plugins.credit_report.account_structure import (
            extract_credit_accounts_from_local_structure_evidence,
        )

        return extract_credit_accounts_from_local_structure_evidence
    raise AttributeError(name)
