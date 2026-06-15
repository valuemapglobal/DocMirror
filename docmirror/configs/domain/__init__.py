# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Domain identity and multilingual entity key normalization.

Re-exports the domain registry used to resolve standardized identity fields
(institution, account holder, invoice number, etc.) from raw extracted entities,
and to normalize locale-specific keys to canonical English via ``key_synonyms.yaml``.

Public API::

    DOMAIN_IDENTITY         Document-type → identity field candidate key lists
    KEY_SYNONYMS            Flattened raw_key → canonical_key lookup dict
    resolve_identity()      Extract identity dict for a document type
    normalize_entity_keys() Apply synonym mapping without mutating input
"""

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
