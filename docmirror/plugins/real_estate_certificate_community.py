# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Real Estate Certificate Domain Plugin (Community Edition)
==========================================================

Community edition baseline: scene detection, identity fields,
and basic domain data construction.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from docmirror.plugins import DomainPlugin


class RealEstateCertificateCommunityPlugin(DomainPlugin):
    """Community edition plugin for real estate certificate processing."""

    @property
    def domain_name(self) -> str:
        return "real_estate_certificate"

    @property
    def display_name(self) -> str:
        return "Real Estate Certificate (Community)"

    @property
    def edition(self) -> str:
        return "community"

    @property
    def identity_fields(self) -> Sequence[tuple[str, Sequence[str]]]:
        return (
            ("obligee", ("权利人", "权利人姓名", "Obligee")),
            ("certificate_number", ("不动产权证号", "权证号", "Certificate No")),
            ("property_location", ("坐落", "房屋坐落", "Location", "不动产坐落")),
            ("property_area", ("面积", "建筑面积", "Area")),
            ("property_use", ("用途", "Property Use", "规划用途")),
            ("unit_number", ("不动产单元号", "Unit No")),
        )

    def build_domain_data(self, metadata, entities):
        from docmirror.models.entities.domain_models import DomainData
        return DomainData(
            document_type="real_estate_certificate",
            raw_entities={
                "obligee": entities.get("obligee", ""),
                "certificate_number": entities.get("certificate_number", ""),
                "property_location": entities.get("property_location", ""),
                "property_area": entities.get("property_area", ""),
            },
        )


plugin = RealEstateCertificateCommunityPlugin()
