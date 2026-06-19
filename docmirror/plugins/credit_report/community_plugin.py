# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Credit report community domain plugin.

Premium community plugin for personal credit reports (key-value archetype). Extracts
identity fields (name, ID number, report time), optional lightweight section hints,
and table records via shared KV extract helpers.

Pipeline role: ``runner`` community path; ``post_extract.hooks.credit_sections`` may
attach full sections to Mirror when enterprise splitter is available.

Key exports: ``CreditReportPlugin``, ``plugin``.

Dependencies: ``DomainPlugin``, ``dec_builder``, ``kv_community_extract``,
``kv_community_enrich.enrich_credit_report_output``.
"""

from __future__ import annotations

from collections.abc import Sequence

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

    def build_domain_data(self, _metadata, entities):
        from docmirror.plugins._base.dec_builder import build_dec_kv
        return build_dec_kv("credit_report", {
            "name": entities.get("name", ""),
            "id_number": entities.get("id_number", ""),
            "report_time": entities.get("report_time", ""),
        })

    def extract_from_mirror(self, parse_result, text: str = ""):
        from docmirror.plugins._base.kv_community_enrich import enrich_credit_report_output
        from docmirror.plugins._base.kv_community_extract import extract_kv_community_output

        out = extract_kv_community_output(
            self,
            parse_result,
            identity_specs=self.identity_fields,
            full_text=text,
            support_level="L2",
        )
        return enrich_credit_report_output(out, parse_result=parse_result, full_text=text)


plugin = CreditReportPlugin()
