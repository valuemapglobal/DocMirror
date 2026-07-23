# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Business license community domain plugin.

Premium community plugin for Chinese business registration certificates (key-value
archetype). Maps identity labels (company name, USCC, legal representative, etc.),
validates USCC checksum in enrich step, and emits v2.0 community JSON.

Pipeline role: the canonical runner invokes ``recognize_facts`` and applies the
returned ``CanonicalPatch`` before sealing.

Key exports: ``BusinessLicensePlugin``, ``plugin``.

Dependencies: ``Core canonical capability``, ``CanonicalPatch``, ``kv_community_extract``,
``kv_community_enrich.enrich_business_license_output``.
"""

from __future__ import annotations

from collections.abc import Sequence

from docmirror.input.canonical.fact_patch import CanonicalPatch


class BusinessLicensePlugin:
    """Community edition plugin for business license document processing."""

    @property
    def domain_name(self) -> str:
        return "business_license"

    @property
    def display_name(self) -> str:
        return "Business License (Community)"

    @property
    def capability_id(self) -> str:
        return self.domain_name

    @property
    def identity_fields(self) -> Sequence[tuple[str, Sequence[str]]]:
        return (
            ("company_name", ("名称", "公司名称", "Company Name", "Name")),
            ("company_type", ("主体类型", "类型", "公司类型", "Company Type")),
            (
                "unified_social_credit_code",
                ("统一社会信用代码", "信用代码", "Unified Social Credit Code", "USCC"),
            ),
            ("legal_representative", ("法定代表人", "负责人", "负责K人", "Legal Representative")),
            ("registered_capital", ("注册资本", "Registered Capital")),
            (
                "date_of_establishment",
                ("成立日期", "成立时间", "Date of Establishment", "Establishment Date"),
            ),
            ("business_term", ("营业期限", "Business Term")),
            ("address", ("经营场所", "住所", "地址", "Registered Address", "Address")),
            ("business_scope", ("经营范围", "Business Scope")),
            ("registration_authority", ("登记机关", "Registration Authority")),
            ("additional_registration_details", ("Additional Registration Details",)),
            ("postal_code", ("邮政编码", "Postal Code")),
            ("contact_phone", ("联系电话", "Contact Phone")),
            ("annual_inspection", ("年检", "Annual Inspection")),
            ("special_qualification", ("特殊资质", "Special Qualification")),
        )

    def recognize_facts(self, parse_result, text: str = "") -> CanonicalPatch:
        from docmirror.plugins._base.kv_community_extract import extract_kv_fact_patch

        return extract_kv_fact_patch(
            self,
            parse_result,
            identity_specs=self.identity_fields,
            full_text=text,
        )


plugin = BusinessLicensePlugin()
