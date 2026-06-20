# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Archived ID card community domain plugin.

Legacy community ``DomainPlugin`` with scene keywords, identity field specs, and
``build_domain_data`` for national ID cards. Not part of the current six premium
plus generic community strategy and not registered at runtime.

Pipeline role: none — reference implementation only.

Key exports: ``IDCardPlugin``, ``plugin``.
"""

from __future__ import annotations

from collections.abc import Sequence

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

    def build_domain_data(self, _metadata, entities):
        from docmirror.plugins._base.dec_builder import build_dec_kv

        return build_dec_kv(
            "id_card",
            {
                "name": entities.get("name", metadata.get("Name", "")),
                "id_number": entities.get("id_number", metadata.get("ID Number", "")),
                "gender": entities.get("gender", ""),
                "address": entities.get("address", ""),
            },
        )


plugin = IDCardPlugin()
