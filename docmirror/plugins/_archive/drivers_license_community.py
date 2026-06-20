# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Archived driver's license community domain plugin.

Legacy community ``DomainPlugin`` for driver's license documents. Superseded by
enterprise plugins or generic fallback; kept under ``_archive`` for historical tests.

Pipeline role: none — not discovered by ``plugin_registry``.

Key exports: ``DriversLicensePlugin``, ``plugin``.
"""

from __future__ import annotations

from collections.abc import Sequence

from docmirror.plugins import DomainPlugin


class DriversLicensePlugin(DomainPlugin):
    """Community edition plugin for driver's license document processing."""

    @property
    def domain_name(self) -> str:
        return "drivers_license"

    @property
    def display_name(self) -> str:
        return "Driver's License (Community)"

    @property
    def edition(self) -> str:
        return "community"

    @property
    def identity_fields(self) -> Sequence[tuple[str, Sequence[str]]]:
        return (
            ("name", ("姓名", "Name")),
            ("id_number", ("身份证号", "ID Number", "证件号码")),
            ("license_number", ("驾驶证号", "License No", "档案编号")),
            ("driving_type", ("准驾车型", "Class", "准驾")),
            ("valid_from", ("有效日期", "Valid From", "有效起始")),
            ("valid_until", ("有效期限", "Valid Until", "有效截止")),
        )

    def build_domain_data(self, _metadata, entities):
        from docmirror.plugins._base.dec_builder import build_dec_kv

        return build_dec_kv(
            "drivers_license",
            {
                "name": entities.get("name", ""),
                "id_number": entities.get("id_number", ""),
                "license_number": entities.get("license_number", ""),
                "driving_type": entities.get("driving_type", ""),
            },
        )


plugin = DriversLicensePlugin()
