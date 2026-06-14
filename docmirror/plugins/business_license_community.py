# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Business License Domain Plugin (Community Edition)
===================================================

Community edition baseline: scene detection, identity fields,
and basic domain data construction.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from docmirror.plugins import DomainPlugin


class BusinessLicensePlugin(DomainPlugin):
    """Community edition plugin for business license document processing."""

    @property
    def domain_name(self) -> str:
        return "business_license"

    @property
    def display_name(self) -> str:
        return "Business License (Community)"

    @property
    def edition(self) -> str:
        return "community"

    @property
    def identity_fields(self) -> Sequence[tuple[str, Sequence[str]]]:
        return (
            ("company_name", ("名称", "公司名称", "Name")),
            ("unified_social_credit_code", ("统一社会信用代码", "信用代码", "USCC")),
            ("legal_representative", ("法定代表人", "负责人", "Legal Representative")),
            ("registered_capital", ("注册资本", "Registered Capital")),
            ("date_of_establishment", ("成立日期", "成立时间", "Date of Establishment")),
            ("business_term", ("营业期限", "Business Term")),
            ("address", ("住所", "地址", "Address")),
            ("business_scope", ("经营范围", "Business Scope")),
        )

    def build_domain_data(self, metadata, entities):
        from docmirror.plugins._base.dec_builder import build_dec_kv
        return build_dec_kv("business_license", {
            "company_name": entities.get("company_name", ""),
            "unified_social_credit_code": entities.get("unified_social_credit_code", ""),
            "legal_representative": entities.get("legal_representative", ""),
        })

    def extract_from_mirror(self, parse_result, text: str = ""):
        from docmirror.plugins._base.kv_community_enrich import enrich_business_license_output
        from docmirror.plugins._base.kv_community_extract import extract_kv_community_output

        out = extract_kv_community_output(
            self,
            parse_result,
            identity_specs=self.identity_fields,
            full_text=text,
        )
        return enrich_business_license_output(out, parse_result=parse_result, full_text=text)



plugin = BusinessLicensePlugin()
