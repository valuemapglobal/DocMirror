# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Mortgage Contract Domain Plugin (Community Edition)
====================================================

Community edition baseline: scene detection, identity fields,
and basic domain data construction.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from docmirror.plugins import DomainPlugin


class MortgageContractCommunityPlugin(DomainPlugin):
    """Community edition plugin for mortgage contract document processing."""

    @property
    def domain_name(self) -> str:
        return "mortgage_contract"

    @property
    def display_name(self) -> str:
        return "Mortgage Contract (Community)"

    @property
    def edition(self) -> str:
        return "community"

    @property
    def identity_fields(self) -> Sequence[tuple[str, Sequence[str]]]:
        return (
            ("mortgagor", ("抵押人", "Mortgagor", "甲方")),
            ("mortgagee", ("抵押权人", "Mortgagee", "乙方")),
            ("mortgage_amount", ("抵押金额", "担保金额", "Mortgage Amount")),
            ("collateral", ("抵押物", "抵押财产", "Collateral", "抵押物名称")),
            ("contract_number", ("合同编号", "Contract No", "协议编号")),
        )

    def build_domain_data(self, metadata, entities):
        from docmirror.models.entities.domain_models import ContractData, DomainData
        return DomainData(
            document_type="mortgage_contract",
            contract=ContractData(
                contract_number=str(entities.get("contract_number", "")),
                party_a=str(entities.get("mortgagor", "")),
                party_b=str(entities.get("mortgagee", "")),
                contract_amount=str(entities.get("mortgage_amount", "")),
            ),
        )


plugin = MortgageContractCommunityPlugin()
