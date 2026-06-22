# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Data Classification Registry — canonical sensitivity levels for all data.

Every input, artifact, field, fixture, and log event MUST have a data classification.
The five levels form a strict ordering: public < internal < confidential < restricted < secret.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Any


class DataClassification(IntEnum):
    """Canonical data sensitivity levels in increasing order of restriction.

    Levels:
        public: Synthetic fixtures, public docs — safe for public repos.
        internal: Pipeline decisions, metrics, internal IDs.
        confidential: Enterprise names, transaction summaries, filenames.
        restricted: ID numbers, phone, bank account, OCR raw text, page images.
        secret: API keys, private keys, license signing keys.
    """

    PUBLIC = 0
    INTERNAL = 1
    CONFIDENTIAL = 2
    RESTRICTED = 3
    SECRET = 4

    @property
    def label(self) -> str:
        return self.name.lower()

    @property
    def allowed_in_logs(self) -> bool:
        """Whether this level can appear in production logs."""
        return self <= DataClassification.INTERNAL

    @property
    def allowed_in_support_bundle(self) -> bool:
        """Whether this level can appear in a GA support bundle (redacted profile)."""
        return self <= DataClassification.CONFIDENTIAL

    @property
    def requires_redaction(self) -> bool:
        """Whether values at this level must be redacted/masked."""
        return self >= DataClassification.CONFIDENTIAL


def classify_document(filename: str, page_count: int, has_sensitive_fields: bool = False) -> DataClassification:
    """Classify a document based on its metadata.

    Heuristic classification — conservative by default. Documents with sensitive field
    patterns (bank statement, ID cards, invoices) are classified as RESTRICTED.
    """
    if has_sensitive_fields:
        return DataClassification.RESTRICTED
    return DataClassification.CONFIDENTIAL


def classify_value(value: str, *, has_pii_pattern: bool = False) -> DataClassification:
    """Classify a single data value.

    Args:
        value: The raw value string.
        has_pii_pattern: Whether the value matches known PII patterns (ID, phone, acct).
    """
    if not value:
        return DataClassification.PUBLIC
    if has_pii_pattern:
        return DataClassification.RESTRICTED
    if len(value) > 200:
        return DataClassification.CONFIDENTIAL
    return DataClassification.INTERNAL


def is_classified_above(level: DataClassification, threshold: DataClassification) -> bool:
    """Check if a data classification is at or above the threshold.

    Returns True if the data is MORE sensitive than the threshold allows.
    """
    return level >= threshold
