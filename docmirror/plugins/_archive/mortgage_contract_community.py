# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Archived mortgage contract community domain plugin.

Legacy community ``DomainPlugin`` for mortgage/loan security contract documents.
Retained in ``_archive`` after community plugin system refactor.

Pipeline role: none — reference and migration tests only.

Key exports: ``MortgageContractCommunityPlugin``, ``plugin``.
"""

from __future__ import annotations

from collections.abc import Sequence

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

    def build_domain_data(self, _metadata, entities):
        from docmirror.plugins._base.dec_builder import build_dec_kv

        return build_dec_kv(
            "mortgage_contract",
            {
                "contract_number": str(entities.get("contract_number", "")),
                "party_a": str(entities.get("mortgagor", "")),
                "party_b": str(entities.get("mortgagee", "")),
                "contract_amount": str(entities.get("mortgage_amount", "")),
            },
        )


plugin = MortgageContractCommunityPlugin()
