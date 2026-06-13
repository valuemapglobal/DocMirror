# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Re-export shim — see ``docmirror.configs.models.layout_profile``."""

from docmirror.configs.models.layout_profile import (
    InstitutionVariant,
    LayoutProfile,
    LayoutProfileMatchRules,
)

__all__ = ["LayoutProfile", "LayoutProfileMatchRules", "InstitutionVariant"]
