# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
LayoutProfile re-export shim — configuration models at the entities boundary.

Re-exports ``LayoutProfile``, ``LayoutProfileMatchRules``, and
``InstitutionVariant`` from ``docmirror.configs.models.layout_profile`` so
layout-aware middleware and plugins import profile types from the models
package consistently with other entity exports.

Canonical SSOT: ``docmirror.configs.models.layout_profile``.
"""

from docmirror.configs.models.layout_profile import (
    InstitutionVariant,
    LayoutProfile,
    LayoutProfileMatchRules,
)

__all__ = ["LayoutProfile", "LayoutProfileMatchRules", "InstitutionVariant"]
