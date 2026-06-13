# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
ID Card Domain Plugin (Community Edition)
==========================================

Community edition baseline: scene detection, identity fields,
and basic domain data construction.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from docmirror.plugins import DomainPlugin


class IDCardPlugin(DomainPlugin):
    """Community edition plugin for ID card document processing."""

    @property
    def domain_name(self) -> str:
        return "id_card"

    @property
    def display_name(self) -> str:
        return "ID Card (Community)"

    @property
    def edition(self) -> str:
        return "community"

    @property
    def identity_fields(self) -> Sequence[tuple[str, Sequence[str]]]:
        return (
            ("name", ("姓名", "Name")),
            ("id_number", ("公民身份号码", "身份证号", "ID Number")),
            ("gender", ("性别", "Gender", "Sex")),
            ("nationality", ("民族", "Nationality")),
            ("birth_date", ("出生", "出生日期", "Birth", "Date of Birth")),
            ("address", ("住址", "Address", "地址")),
        )

    def build_domain_data(self, metadata, entities):
        from docmirror.models.entities.domain_models import DomainData
        return DomainData(
            document_type="id_card",
            raw_entities={
                "name": entities.get("name", metadata.get("Name", "")),
                "id_number": entities.get("id_number", metadata.get("ID Number", "")),
                "gender": entities.get("gender", ""),
                "address": entities.get("address", ""),
            },
        )


plugin = IDCardPlugin()
