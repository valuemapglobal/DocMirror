# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Social Security Proof Domain Plugin (Community Edition)
========================================================

Community edition baseline: scene detection, identity fields,
and basic domain data construction.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from docmirror.plugins import DomainPlugin


class SocialSecurityProofCommunityPlugin(DomainPlugin):
    """Community edition plugin for social security proof document processing."""

    @property
    def domain_name(self) -> str:
        return "social_security_proof"

    @property
    def display_name(self) -> str:
        return "Social Security Proof (Community)"

    @property
    def edition(self) -> str:
        return "community"

    @property
    def identity_fields(self) -> Sequence[tuple[str, Sequence[str]]]:
        return (
            ("name", ("姓名", "Name", "参保人")),
            ("id_number", ("身份证号", "证件号码", "社会保障号码", "ID Number")),
            ("company_name", ("单位名称", "缴费单位", "Company")),
            ("payment_period", ("缴费时间段", "缴纳月份", "Period")),
            ("payment_base", ("缴费基数", "Payment Base")),
        )

    def build_domain_data(self, metadata, entities):
        from docmirror.plugins._base.dec_builder import build_dec_kv
        return build_dec_kv("social_security_proof", {
            "name": entities.get("name", ""),
            "id_number": entities.get("id_number", ""),
            "company_name": entities.get("company_name", ""),
        })



plugin = SocialSecurityProofCommunityPlugin()
