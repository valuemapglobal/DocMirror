# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Redactor — PII, secret, and value masking for logs, support bundles, and debug.

Provides pluggable redaction rules that can be applied to strings, dicts, and
lists. Used by the secure logging filter, support bundle builder, and debug
crop generator.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

# Patterns for automatic detection
_SECRET_PATTERNS = [
    (re.compile(r"(?:api[_-]?key|apikey|secret|token|password|auth)\s*[:=]\s*\S+", re.IGNORECASE), "[SECRET_REDACTED]"),
    (re.compile(r"Bearer\s+\S+", re.IGNORECASE), "Bearer [REDACTED]"),
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "sk-[REDACTED]"),
]

_PII_PATTERNS = [
    (re.compile(r"\b\d{17}[\dXx]\b"), "ID_MASKED"),  # Chinese ID: 18 digits
    (re.compile(r"\b1[3-9]\d{9}\b"), "PHONE_MASKED"),  # Chinese mobile
    (re.compile(r"\b\d{16,19}\b"), "CARD_MASKED"),  # Bank card
    (re.compile(r"\b[1-9]\d{5}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{4}\b"), "ID_TAIL_MASKED"),
]


def redact_secrets(text: str) -> str:
    """Redact API keys, tokens, and other secrets from a string."""
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact_pii(text: str) -> str:
    """Redact personally identifiable information from a string.

    Replaces ID numbers, phone numbers, bank card numbers with type labels.
    Preserves the last 4 digits where safe.
    """
    for pattern, replacement in _PII_PATTERNS:

        def _replacer(m: re.Match) -> str:
            matched = m.group(0)
            if len(matched) >= 6:
                return f"{replacement}(...{matched[-4:]})"
            return replacement

        text = pattern.sub(_replacer, text)
    return text


def mask_value(value: str, *, keep_last: int = 4) -> str:
    """Mask a value, optionally preserving the last N characters.

    For values shorter than keep_last*2, masks completely.
    """
    if not value:
        return ""
    if len(value) <= keep_last * 2:
        return "*" * len(value)
    return "*" * (len(value) - keep_last) + value[-keep_last:]


def hash_value(value: str, *, length: int = 16) -> str:
    """Create a non-reversible hash of a value for redaction."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def redact_text(text: str, *, mask_pii: bool = True, mask_secrets: bool = True) -> str:
    """Apply all redaction rules to a text string."""
    if mask_secrets:
        text = redact_secrets(text)
    if mask_pii:
        text = redact_pii(text)
    return text


def redact_dict(data: dict[str, Any], *, secret_keys: set[str] | None = None) -> dict[str, Any]:
    """Recursively redact a dictionary, masking values under secret keys."""
    secret_keys = secret_keys or {
        "api_key",
        "apikey",
        "secret",
        "token",
        "password",
        "auth",
        "license_key",
        "private_key",
        "signing_key",
        "access_key",
    }
    result: dict[str, Any] = {}
    for key, value in data.items():
        key_lower = key.lower().replace("_", "").replace("-", "")
        if any(sk in key_lower for sk in secret_keys):
            result[key] = "[SECRET_REDACTED]"
        elif isinstance(value, dict):
            result[key] = redact_dict(value, secret_keys=secret_keys)
        elif isinstance(value, list):
            result[key] = [redact_dict(v, secret_keys=secret_keys) if isinstance(v, dict) else v for v in value]
        elif isinstance(value, str):
            result[key] = redact_text(value)
        else:
            result[key] = value
    return result


def classify_redaction(text: str) -> dict[str, Any]:
    """Analyze a string and report what would be redacted."""
    report: dict[str, Any] = {
        "has_secrets": False,
        "has_pii": False,
        "pii_types": [],
    }
    for pattern, _ in _SECRET_PATTERNS:
        if pattern.search(text):
            report["has_secrets"] = True
            break
    for pattern, label in _PII_PATTERNS:
        m = pattern.search(text)
        if m:
            report["has_pii"] = True
            report["pii_types"].append(label)
    return report
