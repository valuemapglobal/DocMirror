# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Archived passport community domain plugin.

Legacy community ``DomainPlugin`` for passport documents with identity field mapping
and ``build_domain_data`` KV output. Not shipped in current community edition.

Pipeline role: none — reference only.

Key exports: ``PassportPlugin``, ``plugin``.
"""

from __future__ import annotations

from collections.abc import Sequence

from docmirror.plugins import DomainPlugin


class PassportPlugin(DomainPlugin):
    """Community edition plugin for passport document processing."""

    @property
    def domain_name(self) -> str:
        return "passport"

    @property
    def display_name(self) -> str:
        return "Passport (Community)"

    @property
    def edition(self) -> str:
        return "community"

    @property
    def identity_fields(self) -> Sequence[tuple[str, Sequence[str]]]:
        return (
            ("surname", ("Surname", "姓")),
            ("given_name", ("Given name", "名", "Given Names")),
            ("passport_number", ("Passport No", "护照号", "Passport Number")),
            ("nationality", ("Nationality", "国籍")),
            ("birth_date", ("Date of birth", "出生日期")),
            ("sex", ("Sex", "性别")),
            ("place_of_birth", ("Place of birth", "出生地点")),
            ("date_of_issue", ("Date of issue", "签发日期")),
            ("date_of_expiry", ("Date of expiry", "有效期至")),
        )

    def build_domain_data(self, _metadata, entities):
        from docmirror.plugins._base.dec_builder import build_dec_kv

        return build_dec_kv(
            "passport",
            {
                "surname": entities.get("surname", ""),
                "given_name": entities.get("given_name", ""),
                "passport_number": entities.get("passport_number", ""),
                "nationality": entities.get("nationality", ""),
            },
        )


plugin = PassportPlugin()
