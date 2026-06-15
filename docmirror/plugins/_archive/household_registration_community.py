# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Archived household registration (hukou) community domain plugin.

Legacy community ``DomainPlugin`` for household registration booklet documents.
Archived before the 6+1 premium community consolidation.

Pipeline role: none — not registered at runtime.

Key exports: ``HouseholdRegistrationPlugin``, ``plugin``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from docmirror.plugins import DomainPlugin


class HouseholdRegistrationPlugin(DomainPlugin):
    """Community edition plugin for household registration document processing."""

    @property
    def domain_name(self) -> str:
        return "household_registration"

    @property
    def display_name(self) -> str:
        return "Household Registration (Community)"

    @property
    def edition(self) -> str:
        return "community"

    @property
    def identity_fields(self) -> Sequence[tuple[str, Sequence[str]]]:
        return (
            ("householder", ("户主", "户主姓名", "Householder")),
            ("household_number", ("户号", "Household No")),
            ("address", ("住址", "Address", "户口所在地")),
            ("name", ("姓名", "Name")),
            ("id_number", ("公民身份号码", "身份证号", "ID Number")),
            ("relationship", ("与户主关系", "Relation", "Relationship")),
        )

    def build_domain_data(self, metadata, entities):
        from docmirror.plugins._base.dec_builder import build_dec_kv
        return build_dec_kv("household_registration", {
            "householder": entities.get("householder", ""),
            "household_number": entities.get("household_number", ""),
            "address": entities.get("address", ""),
        })



plugin = HouseholdRegistrationPlugin()
