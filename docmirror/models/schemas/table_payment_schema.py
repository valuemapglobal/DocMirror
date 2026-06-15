# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
DEC validation for cashflow table payment plugins (design 09 Wave 2 P1-4).

Validates ``DomainExtractionResult`` payloads for WeChat Pay and Alipay payment
export document types (``wechat_payment``, ``alipay_payment``).

Checks::

    structured_data is a dict with a list ``records`` field
    Empty records with ``validation_passed=True`` is flagged as an issue
    Optional ``summary`` sub-dict type correctness

Entry point: ``validate_dec(dec: DomainExtractionResult) -> list[str]``
"""

from __future__ import annotations

from docmirror.models.entities.domain_result import DomainExtractionResult

_TABLE_PAYMENT_TYPES = frozenset({"wechat_payment", "alipay_payment"})


def validate_dec(dec: DomainExtractionResult) -> list[str]:
    issues: list[str] = []
    if dec.document_type not in _TABLE_PAYMENT_TYPES:
        return issues

    sd = dec.structured_data
    if not isinstance(sd, dict):
        issues.append(f"{dec.document_type}: structured_data must be a dict")
        return issues

    records = sd.get("records")
    if not isinstance(records, list):
        issues.append(f"{dec.document_type}: structured_data.records must be a list")
    elif len(records) == 0 and dec.quality.validation_passed:
        issues.append(f"{dec.document_type}: validation_passed but records empty")

    summary = sd.get("summary")
    if summary is not None and not isinstance(summary, dict):
        issues.append(f"{dec.document_type}: structured_data.summary must be a dict")

    return issues
