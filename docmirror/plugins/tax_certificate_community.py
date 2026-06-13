# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Tax Certificate Domain Plugin (Community Edition)
==================================================

Community edition baseline: scene detection, identity fields,
and basic domain data construction.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from docmirror.plugins import DomainPlugin


class TaxCertificateCommunityPlugin(DomainPlugin):
    """Community edition plugin for tax certificate document processing."""

    @property
    def domain_name(self) -> str:
        return "tax_certificate"

    @property
    def display_name(self) -> str:
        return "Tax Certificate (Community)"

    @property
    def edition(self) -> str:
        return "community"

    @property
    def identity_fields(self) -> Sequence[tuple[str, Sequence[str]]]:
        return (
            ("taxpayer_name", ("纳税人名称", "纳税人", "Name", "姓名")),
            ("taxpayer_id", ("纳税人识别号", "Tax ID", "身份证号")),
            ("tax_type", ("税种", "Tax Type", "品目")),
            ("tax_amount", ("实缴金额", "实缴税款", "Tax Amount")),
            ("tax_period", ("税款所属期", "所属期", "Period")),
            ("issue_date", ("开具日期", "填发日期", "Date")),
        )

    def build_domain_data(self, metadata, entities):
        from docmirror.models.entities.domain_models import DomainData
        return DomainData(
            document_type="tax_certificate",
            raw_entities={
                "taxpayer_name": entities.get("taxpayer_name", ""),
                "taxpayer_id": entities.get("taxpayer_id", ""),
                "tax_amount": entities.get("tax_amount", ""),
            },
        )


plugin = TaxCertificateCommunityPlugin()
