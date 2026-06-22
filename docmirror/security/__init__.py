# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Privacy / Security / Compliance (PSC) module for DocMirror GA 1.0.

Provides the unified security contract for all DocMirror operations:
  - Data classification registry (public -> secret)
  - Privacy mode resolver (local / egress_opt_in / offline_enterprise / debug_internal)
  - Egress gateway for all network outbound access
  - Secure logging redaction filter
  - Redactor for PII / secret / value masking
  - Input resource gate (archive, PDF, image, REST upload)
  - Security evidence ledger for per-parse audit
"""

from docmirror.security.data_classification import (
    DataClassification,
    classify_document,
    classify_value,
    is_classified_above,
)
from docmirror.security.security_ledger import (
    SecurityEvidenceLedger,
    EgressEvent,
    ResourceGateDecision,
    build_security_summary,
)

# ---------------------------------------------------------------------------
# Wave 1 — Privacy mode & Egress gate
# ---------------------------------------------------------------------------
from docmirror.security.privacy_mode import (
    DEFAULT_PRIVACY_MODE,
    PrivacyMode,
    PrivacyPolicy,
    resolve_privacy_policy,
    is_provider_allowed,
)
from docmirror.security.egress import (
    EgressBlockedError,
    EgressGate,
)

# ---------------------------------------------------------------------------
# Wave 2 — Redaction & Secure logging
# ---------------------------------------------------------------------------
from docmirror.security.redaction import (
    redact_secrets,
    redact_pii,
    mask_value,
    hash_value,
    redact_text,
    redact_dict,
    classify_redaction,
)
from docmirror.security.logging import (
    SafeLoggingFilter,
    install_safe_logging,
    log_security_event,
)

# ---------------------------------------------------------------------------
# Wave 3 — Input resource gate
# ---------------------------------------------------------------------------
from docmirror.security.resource_gate import (
    DEFAULT_LIMITS as DEFAULT_RESOURCE_LIMITS,
    ResourceGateBlockedError,
    ArchivePreflightResult,
    PDFPreflightResult,
    ImagePreflightResult,
    check_archive_preflight,
    check_pdf_preflight,
    check_image_preflight,
    check_rest_upload,
    to_ledger_decision,
)

__all__ = [
    # Data classification (Wave 0)
    "DataClassification",
    "classify_document",
    "classify_value",
    "is_classified_above",
    # Security ledger (Wave 0)
    "SecurityEvidenceLedger",
    "EgressEvent",
    "ResourceGateDecision",
    "build_security_summary",
    # Privacy mode (Wave 1)
    "DEFAULT_PRIVACY_MODE",
    "PrivacyMode",
    "PrivacyPolicy",
    "resolve_privacy_policy",
    "is_provider_allowed",
    # Egress gateway (Wave 1)
    "EgressBlockedError",
    "EgressGate",
    # Redaction (Wave 2)
    "redact_secrets",
    "redact_pii",
    "mask_value",
    "hash_value",
    "redact_text",
    "redact_dict",
    "classify_redaction",
    # Secure logging (Wave 2)
    "SafeLoggingFilter",
    "install_safe_logging",
    "log_security_event",
    # Resource gate (Wave 3)
    "DEFAULT_RESOURCE_LIMITS",
    "ResourceGateBlockedError",
    "ArchivePreflightResult",
    "PDFPreflightResult",
    "ImagePreflightResult",
    "check_archive_preflight",
    "check_pdf_preflight",
    "check_image_preflight",
    "check_rest_upload",
    "to_ledger_decision",
]
