# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Credit Report Domain Plugin (Community Edition)
================================================

Community edition baseline: scene detection, identity fields,
and basic domain data construction.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from docmirror.plugins import DomainPlugin


class CreditReportPlugin(DomainPlugin):
    """Community edition plugin for credit report document processing."""

    @property
    def domain_name(self) -> str:
        return "credit_report"

    @property
    def display_name(self) -> str:
        return "Credit Report (Community)"

    @property
    def edition(self) -> str:
        return "community"

    @property
    def identity_fields(self) -> Sequence[tuple[str, Sequence[str]]]:
        return (
            ("name", ("姓名", "Name", "报告主体")),
            ("id_number", ("身份证号", "证件号码", "ID Number")),
            ("report_time", ("报告时间", "查询时间", "Report Time")),
            ("report_number", ("报告编号", "Report No")),
        )

    def build_domain_data(self, metadata, entities):
        from docmirror.models.entities.domain_models import DomainData
        return DomainData(
            document_type="credit_report",
            raw_entities={
                "name": entities.get("name", ""),
                "id_number": entities.get("id_number", ""),
                "report_time": entities.get("report_time", ""),
            },
        )


plugin = CreditReportPlugin()
