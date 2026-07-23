# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Credit report community domain plugin.

Premium community plugin for personal brief, personal detail, and enterprise
credit reports. Extracts identity fields, report subtype/content mode, optional
lightweight section hints, and table records via shared KV extract helpers.

Pipeline role: post-seal domain derivation and Community JSON projection.

Key exports: ``CreditReportPlugin``, ``plugin``.

Dependencies: ``ProjectionData``, ``kv_projection``,
``kv_community_enrich.enrich_credit_report_output``.
"""

from __future__ import annotations

from collections.abc import Sequence

from docmirror.plugins._base.projector import CommunityProjector, ProjectionData


class CreditReportPlugin(CommunityProjector):
    """Community edition plugin for credit report document processing."""

    @property
    def domain_name(self) -> str:
        return "credit_report"

    @property
    def display_name(self) -> str:
        return "Credit Report (Community)"

    @property
    def projector_id(self) -> str:
        return self.domain_name

    @property
    def identity_fields(self) -> Sequence[tuple[str, Sequence[str]]]:
        return (
            ("subject_name", ("被查询者姓名", "企业名称", "姓名", "Name", "报告主体")),
            ("id_number", ("被查询者证件号码", "身份证号", "证件号码", "ID Number")),
            ("id_type", ("被查询者证件类型", "证件类型", "ID Type")),
            ("unified_social_credit_code", ("统一社会信用代码",)),
            ("zhongzheng_code", ("中征码", "贷款卡编码", "贷款卡号")),
            ("query_institution", ("查询机构",)),
            ("report_time", ("报告时间", "查询时间", "Report Time")),
            ("report_number", ("报告编号", "Report No", "NO.")),
        )

    def derive(self, parse_result, text: str = "") -> ProjectionData:
        from docmirror.plugins.credit_report.projection import derive_credit_report_projection

        return derive_credit_report_projection(self, parse_result, text)


plugin = CreditReportPlugin()
