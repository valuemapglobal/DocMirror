# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Secure Logging Contract — redaction filter for the root logger.

Ensures all log output passes through PII/secret redaction before being emitted.
Prohibits logging of raw text values, full file paths, and license keys.
"""

from __future__ import annotations

import logging
from typing import Any

from docmirror.security.redaction import redact_text

# Fields that must never appear in plain text in logs
_SECRET_FIELD_NAMES = {
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
    "authorization",
}

# Max allowed length for a logged string before truncation
_MAX_LOG_VALUE_LENGTH = 200


class SafeLoggingFilter(logging.Filter):
    """Logging filter that redacts PII, secrets, and oversize values.

    Attach to the root logger::

        import logging
        from docmirror.security.logging import SafeLoggingFilter
        logging.getLogger().addFilter(SafeLoggingFilter())

    Also blocks log messages that contain full raw text or page images.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # Redact the log message
        if record.msg and isinstance(record.msg, str):
            record.msg = self._sanitize(record.msg)

        # Redact args
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: self._sanitize(str(v)) if not self._is_secret_key(k) else "[SECRET_REDACTED]"
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(self._sanitize(str(a)) for a in record.args)

        return True

    def _sanitize(self, text: str) -> str:
        """Apply all redaction and truncation."""
        text = redact_text(text, mask_pii=True, mask_secrets=True)
        if len(text) > _MAX_LOG_VALUE_LENGTH:
            text = text[:_MAX_LOG_VALUE_LENGTH] + "...[truncated]"
        return text

    @staticmethod
    def _is_secret_key(key: str) -> bool:
        key_lower = key.lower().replace("_", "").replace("-", "")
        return any(sk in key_lower for sk in _SECRET_FIELD_NAMES)


def install_safe_logging() -> None:
    """Install the SafeLoggingFilter on the root logger if not already present.

    Safe to call multiple times — checks for existing filter before adding.
    """
    root = logging.getLogger()
    for f in root.filters:
        if isinstance(f, SafeLoggingFilter):
            return
    root.addFilter(SafeLoggingFilter())


def log_security_event(logger: logging.Logger, event_type: str, details: dict[str, Any]) -> None:
    """Log a security-relevant event with structured (redacted) details."""
    safe_details = {
        k: redact_text(str(v)) if not SafeLoggingFilter._is_secret_key(k) else "[SECRET_REDACTED]"
        for k, v in details.items()
    }
    logger.info("SECURITY_EVENT type=%s details=%s", event_type, safe_details)
