# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Archived social security card community domain plugin.

Legacy community ``DomainPlugin`` for social security card (社保卡) documents.
Kept for historical compatibility tests only.

Pipeline role: none — not registered in production builds.

Key exports: ``SocialSecurityCardPlugin``, ``plugin``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from docmirror.plugins import DomainPlugin


class SocialSecurityCardPlugin(DomainPlugin):
    """Community edition plugin for social security card document processing."""

    @property
    def domain_name(self) -> str:
        return "social_security_card"

    @property
    def display_name(self) -> str:
        return "Social Security Card (Community)"

    @property
    def edition(self) -> str:
        return "community"

    @property
    def identity_fields(self) -> Sequence[tuple[str, Sequence[str]]]:
        return (
            ("name", ("姓名", "Name")),
            ("id_number", ("身份证号", "社会保障号码", "ID Number")),
            ("card_number", ("卡号", "Card No", "社保卡号")),
            ("gender", ("性别", "Gender")),
            ("nationality", ("民族", "Nationality")),
        )

    def build_domain_data(self, metadata, entities):
        from docmirror.plugins._base.dec_builder import build_dec_kv
        return build_dec_kv("social_security_card", {
            "name": entities.get("name", ""),
            "id_number": entities.get("id_number", ""),
            "card_number": entities.get("card_number", ""),
        })



plugin = SocialSecurityCardPlugin()
