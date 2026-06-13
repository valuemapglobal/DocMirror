# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Payroll Slip Domain Plugin (Community Edition)
===============================================

Community edition baseline: scene detection, identity fields,
and basic domain data construction.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from docmirror.plugins import DomainPlugin


class PayrollSlipCommunityPlugin(DomainPlugin):
    """Community edition plugin for payroll slip document processing."""

    @property
    def domain_name(self) -> str:
        return "payroll_slip"

    @property
    def display_name(self) -> str:
        return "Payroll Slip (Community)"

    @property
    def edition(self) -> str:
        return "community"

    @property
    def identity_fields(self) -> Sequence[tuple[str, Sequence[str]]]:
        return (
            ("employee_name", ("姓名", "员工姓名", "Employee Name")),
            ("employee_id", ("工号", "员工编号", "Employee ID")),
            ("department", ("部门", "Department")),
            ("pay_period", ("工资所属期", "月份", "Pay Period")),
            ("gross_pay", ("应发工资", "Gross Pay", "应发")),
            ("net_pay", ("实发工资", "Net Pay", "实发")),
        )

    def build_domain_data(self, metadata, entities):
        from docmirror.models.entities.domain_models import DomainData
        return DomainData(
            document_type="payroll_slip",
            raw_entities={
                "employee_name": entities.get("employee_name", ""),
                "employee_id": entities.get("employee_id", ""),
                "department": entities.get("department", ""),
                "pay_period": entities.get("pay_period", ""),
                "gross_pay": entities.get("gross_pay", ""),
                "net_pay": entities.get("net_pay", ""),
            },
        )


plugin = PayrollSlipCommunityPlugin()
