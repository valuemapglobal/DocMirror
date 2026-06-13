# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Loan Contract Domain Plugin (Community Edition)
================================================

Community edition baseline: scene detection, identity fields,
and basic domain data construction.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from docmirror.plugins import DomainPlugin


class LoanContractCommunityPlugin(DomainPlugin):
    """Community edition plugin for loan contract document processing."""

    @property
    def domain_name(self) -> str:
        return "loan_contract"

    @property
    def display_name(self) -> str:
        return "Loan Contract (Community)"

    @property
    def edition(self) -> str:
        return "community"

    @property
    def identity_fields(self) -> Sequence[tuple[str, Sequence[str]]]:
        return (
            ("borrower", ("借款人", "Borrower", "借款方")),
            ("lender", ("贷款人", "Lender", "出借人", "贷款方")),
            ("loan_amount", ("借款金额", "贷款金额", "Loan Amount")),
            ("interest_rate", ("贷款利率", "利率", "Interest Rate")),
            ("loan_term", ("借款期限", "贷款期限", "期限", "Loan Term")),
            ("contract_number", ("合同编号", "Contract No", "协议编号")),
        )

    def build_domain_data(self, metadata, entities):
        from docmirror.models.entities.domain_models import ContractData, DomainData
        return DomainData(
            document_type="loan_contract",
            contract=ContractData(
                contract_number=str(entities.get("contract_number", "")),
                party_a=str(entities.get("lender", "")),
                party_b=str(entities.get("borrower", "")),
                contract_amount=str(entities.get("loan_amount", "")),
            ),
        )


plugin = LoanContractCommunityPlugin()
