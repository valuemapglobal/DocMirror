# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Archived insurance policy community domain plugin.

Legacy community ``DomainPlugin`` for insurance policy documents with baseline
identity extraction. Retained under ``_archive`` for migration reference.

Pipeline role: none — superseded by enterprise or generic paths.

Key exports: ``InsurancePolicyCommunityPlugin``, ``plugin``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from docmirror.plugins import DomainPlugin


class InsurancePolicyCommunityPlugin(DomainPlugin):
    """Community edition plugin for insurance policy document processing."""

    @property
    def domain_name(self) -> str:
        return "insurance_policy"

    @property
    def display_name(self) -> str:
        return "Insurance Policy (Community)"

    @property
    def edition(self) -> str:
        return "community"

    @property
    def identity_fields(self) -> Sequence[tuple[str, Sequence[str]]]:
        return (
            ("policy_number", ("保单号", "Policy No", "保险单号")),
            ("insured", ("被保险人", "Insured", "被保人")),
            ("policy_holder", ("投保人", "Policy Holder")),
            ("beneficiary", ("受益人", "Beneficiary")),
            ("insurance_amount", ("保险金额", "保额", "Sum Insured")),
            ("premium", ("保险费", "保费", "Premium")),
            ("insurance_period", ("保险期间", "保险期限", "Period")),
        )

    def build_domain_data(self, metadata, entities):
        from docmirror.plugins._base.dec_builder import build_dec_kv
        return build_dec_kv("insurance_policy", {
            "policy_number": entities.get("policy_number", ""),
            "insured": entities.get("insured", ""),
            "policy_holder": entities.get("policy_holder", ""),
            "insurance_amount": entities.get("insurance_amount", ""),
            "premium": entities.get("premium", ""),
        })



plugin = InsurancePolicyCommunityPlugin()
