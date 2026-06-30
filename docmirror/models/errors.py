# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
DocMirror error codes and failure helpers.
==========================================

Unified error codes, recoverability metadata, and ``ParseResult`` failure builders
used by the dispatcher, format adapters, and REST API responses.

Components::

    DocMirrorErrorCode     Canonical enum (FILE_NOT_FOUND, UNSUPPORTED_FORMAT, …)
    get_error_meta()       Recoverable flag and user-facing message per code
    make_error_detail()    Build ``ErrorDetail`` with code and message
    build_failure_result() Construct a failure ``ParseResult`` with timing and trust info

Error metadata includes recoverability hints (e.g. ``FORMAT_REQUIRES_CONVERTER`` and
``ENCRYPTED_PDF`` are recoverable; ``UNSUPPORTED_FORMAT`` is not) for client retry logic.

Internal design reference: error taxonomy G3.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any

# Re-export for callers that need to build PerceptionResult
_ERROR_META: dict[str, dict[str, Any]] = {
    "FILE_NOT_FOUND": {"recoverable": False, "user_message": "File not found."},
    "FILE_TOO_SMALL": {"recoverable": False, "user_message": "File is too small to contain a valid document."},
    "FILE_TOO_LARGE": {"recoverable": False, "user_message": "File exceeds maximum allowed size."},
    "FILE_EMPTY": {"recoverable": False, "user_message": "File is empty."},
    "UNSUPPORTED_FORMAT": {"recoverable": False, "user_message": "File format is not supported."},
    "LOW_QUALITY_INPUT": {"recoverable": True, "user_message": "Input quality is too low for reliable extraction."},
    "LOW_QUALITY_IMAGE": {"recoverable": True, "user_message": "Image quality is too low for reliable extraction."},
    "INVALID_IMAGE": {"recoverable": True, "user_message": "Image cannot be decoded."},
    "DAMAGED_PDF": {"recoverable": True, "user_message": "PDF appears damaged or truncated."},
    "RESOURCE_LIMIT_EXCEEDED": {"recoverable": True, "user_message": "Input exceeds configured resource limits."},
    "PARTIAL_PAGE_FAILURE": {"recoverable": True, "user_message": "One or more pages failed during extraction."},
    "EMPTY_RESULT": {"recoverable": True, "user_message": "Extraction produced no usable result."},
    "PARSER_ERROR": {"recoverable": False, "user_message": "Parser returned an error."},
    "FORMAT_REQUIRES_CONVERTER": {
        "recoverable": True,
        "user_message": "This format requires LibreOffice (soffice) to be installed for conversion.",
    },
    "EXTRACTION_FAILED": {"recoverable": False, "user_message": "Document extraction failed."},
    "ORCHESTRATION_FAILURE": {"recoverable": False, "user_message": "Parsing pipeline failed."},
    "ENCRYPTED_PDF": {"recoverable": True, "user_message": "PDF is password-protected."},
    "ARCHIVE_PASSWORD_PROTECTED": {
        "recoverable": False,
        "user_message": "Password-protected archives are not supported yet. Please provide an unencrypted archive.",
    },
    "ARCHIVE_RESOURCE_LIMIT": {"recoverable": False, "user_message": "Archive exceeds configured safety limits."},
    "ARCHIVE_UNSAFE_PATH": {"recoverable": False, "user_message": "Archive contains an unsafe path."},
    "TIMEOUT": {"recoverable": True, "user_message": "Processing timed out."},
    "unknown": {"recoverable": False, "user_message": "An unexpected error occurred."},
}


class DocMirrorErrorCode(str, Enum):
    """Canonical error codes for DocMirror failures."""

    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    FILE_TOO_SMALL = "FILE_TOO_SMALL"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    FILE_EMPTY = "FILE_EMPTY"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    LOW_QUALITY_INPUT = "LOW_QUALITY_INPUT"
    LOW_QUALITY_IMAGE = "LOW_QUALITY_IMAGE"
    INVALID_IMAGE = "INVALID_IMAGE"
    DAMAGED_PDF = "DAMAGED_PDF"
    RESOURCE_LIMIT_EXCEEDED = "RESOURCE_LIMIT_EXCEEDED"
    PARTIAL_PAGE_FAILURE = "PARTIAL_PAGE_FAILURE"
    EMPTY_RESULT = "EMPTY_RESULT"
    PARSER_ERROR = "PARSER_ERROR"
    FORMAT_REQUIRES_CONVERTER = "FORMAT_REQUIRES_CONVERTER"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    ORCHESTRATION_FAILURE = "ORCHESTRATION_FAILURE"
    ENCRYPTED_PDF = "ENCRYPTED_PDF"
    ARCHIVE_PASSWORD_PROTECTED = "ARCHIVE_PASSWORD_PROTECTED"
    ARCHIVE_RESOURCE_LIMIT = "ARCHIVE_RESOURCE_LIMIT"
    ARCHIVE_UNSAFE_PATH = "ARCHIVE_UNSAFE_PATH"
    TIMEOUT = "TIMEOUT"
    UNKNOWN = "unknown"


def get_error_meta(code: str) -> dict[str, Any]:
    """Return recoverable and user_message for a given code."""
    return _ERROR_META.get(code, _ERROR_META["unknown"]).copy()


def make_error_detail(code: str, message: str = "") -> ErrorDetail:
    """Build ErrorDetail with code and message from canonical meta."""
    from docmirror.models.entities.parse_result import ErrorDetail

    meta = get_error_meta(code)
    return ErrorDetail(
        code=code,
        message=message or meta.get("user_message", ""),
    )


def build_failure_result(
    code: str,
    message: str,
    file_path: str = "",  # noqa: ARG001 — kept for caller keyword compatibility
    file_type: str = "",
    is_forged: bool | None = None,
    forgery_reasons: list[str] | None = None,
    t0: float | None = None,
) -> ParseResult:
    """Build a failure ParseResult with unified error code. Used by Dispatcher and Adapters."""
    from docmirror.models.entities.parse_result import (
        ParseResult,
        ParserInfo,
        ProvenanceInfo,
        ResultStatus,
        TrustResult,
    )

    elapsed = (time.time() - t0) * 1000 if t0 is not None else 0.0

    trust = None
    if is_forged is not None:
        trust = TrustResult(is_forged=is_forged, forgery_reasons=forgery_reasons or [])

    detail = make_error_detail(code, message)
    return ParseResult(
        status=ResultStatus.FAILURE,
        confidence=0.0,
        error=detail,
        parser_info=ParserInfo(elapsed_ms=elapsed),
        trust=trust,
        provenance=ProvenanceInfo(file_type=file_type),
    )
