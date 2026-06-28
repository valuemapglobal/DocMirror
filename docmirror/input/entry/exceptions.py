# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Typed exception hierarchy for DocMirror document processing.

Purpose: Replaces bare ``Exception`` with specific failure modes (input
validation, extraction, OCR, layout, middleware) so callers and the
pipeline can apply targeted recovery strategies.

Main components: ``MultiModalError``, ``InputValidationError``,
``ExtractionError``, ``OCREngineError``, ``TableExtractionError``,
``LayoutAnalysisError``.

Upstream: Validation guards and pipeline stages on failure.

Downstream: ``entry.factory``, middleware, and API error responses.
"""

from __future__ import annotations


class MultiModalError(Exception):
    """MultiModal Exception Base class."""

    def __init__(self, message: str = "", *, detail: str = ""):
        self.detail = detail
        super().__init__(message)


# ── Layer 0: Input Validation (Constructor Theory Guards) ──


class InputValidationError(MultiModalError):
    """File is outside the system's capability boundary."""

    pass


class FileTooSmallError(InputValidationError):
    """Document is below minimum parseable size."""

    pass


class FileTooLargeError(InputValidationError):
    """Document exceeds maximum allowed size."""

    pass


class ResolutionTooLowError(InputValidationError):
    """Image resolution is below OCR minimum."""

    pass


class UnsupportedFormatError(InputValidationError):
    """File format is not supported by any registered adapter."""

    pass


# ── Layer 1: Extraction ──


class ExtractionError(MultiModalError):
    """Error during CoreExtractor physical extraction.

    Examples: PDF open failed, pdfplumber parse failed, page limit exceeded, etc.
    """

    pass


class OCREngineError(ExtractionError):
    """OCR engine failed or is unavailable."""

    pass


class TableExtractionError(ExtractionError):
    """Table detection or reconstruction failed."""

    pass


class LayoutAnalysisError(MultiModalError):
    """Error in Layout Analysis / Zone Partitioning / Table Extraction layer."""

    pass


# ── Layer 2: Enhancement / Middleware ──


class MiddlewareError(MultiModalError):
    """Error during Middleware processing.

    Attributes:
        middleware_name: The name of the Middleware that failed.
    """

    def __init__(self, message: str = "", *, middleware_name: str = "", detail: str = ""):
        self.middleware_name = middleware_name
        super().__init__(message, detail=detail)

    def __str__(self):
        prefix = f"[{self.middleware_name}] " if self.middleware_name else ""
        return f"{prefix}{super().__str__()}"


class ValidationError(MultiModalError):
    """Data validation failed.

    Examples: Inconsistent table column count, low date coverage rate.
    """

    pass


# ── Layer 3: Serialization ──


class SerializationError(MultiModalError):
    """Failed to serialize or deserialize a result."""

    pass
