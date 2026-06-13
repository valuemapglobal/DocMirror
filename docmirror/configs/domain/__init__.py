# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Domain identity fields and multilingual entity key normalization."""

from docmirror.configs.domain.registry import (
    DOMAIN_IDENTITY,
    KEY_SYNONYMS,
    normalize_entity_keys,
    resolve_identity,
)

__all__ = [
    "DOMAIN_IDENTITY",
    "KEY_SYNONYMS",
    "normalize_entity_keys",
    "resolve_identity",
]
