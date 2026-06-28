# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Result type for explicit, type-safe error handling in the parse pipeline.

Purpose: Provides ``Success`` / ``Failure`` wrappers, ``DocMirrorError``
hierarchy, and combinators (``map``, ``and_then``) so pipeline stages can
return recoverable errors without bare exceptions.

Main components: ``Result``, ``Success``, ``Failure``, ``DocMirrorError``,
``ErrorSeverity``, ``success``, ``failure``, ``try_catch``.

Upstream: Any core module that performs I/O or validation.

Downstream: Entry layer, pipeline stages, and middleware that need structured errors.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Generic, TypeVar

logger = logging.getLogger(__name__)

# Type variables
T = TypeVar("T")  # Success type
E = TypeVar("E", bound="DocMirrorError")  # Error type
U = TypeVar("U")  # For map operations


# ═══════════════════════════════════════════════════════════════════════════════
# Error Severity
# ═══════════════════════════════════════════════════════════════════════════════


class ErrorSeverity(Enum):
    """Error severity levels."""

    RECOVERABLE = auto()  # Can recover (e.g., cache miss)
    DEGRADED = auto()  # Degraded mode (e.g., low OCR quality)
    FATAL = auto()  # Fatal error (e.g., file corrupt)


# ═══════════════════════════════════════════════════════════════════════════════
# Base Error Class
# ═══════════════════════════════════════════════════════════════════════════════


class DocMirrorError(Exception):
    """Base error class for all DocMirror errors."""

    def __init__(
        self,
        message: str,
        code: str,
        severity: ErrorSeverity = ErrorSeverity.FATAL,
        details: dict[str, Any] = None,
        recoverable: bool = False,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.severity = severity
        self.details = details or {}
        self.recoverable = recoverable

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(code={self.code!r}, message={self.message!r})"


# ═══════════════════════════════════════════════════════════════════════════════
# Specific Error Types
# ═══════════════════════════════════════════════════════════════════════════════


class FileError(DocMirrorError):
    """File-related errors."""

    pass


class FileTooLargeError(FileError):
    def __init__(self, size: int, max_size: int):
        super().__init__(
            message=f"File too large: {size / 1024 / 1024:.1f}MB (max {max_size / 1024 / 1024:.0f}MB)",
            code="FILE_TOO_LARGE",
            severity=ErrorSeverity.FATAL,
            details={"size": size, "max_size": max_size},
        )


class FileTooSmallError(FileError):
    def __init__(self, size: int, min_size: int):
        super().__init__(
            message=f"File too small: {size}B (min {min_size}B)",
            code="FILE_TOO_SMALL",
            severity=ErrorSeverity.FATAL,
            details={"size": size, "min_size": min_size},
        )


class FileNotFoundError2(FileError):
    """Note: Can't use FileNotFoundError (built-in)."""

    def __init__(self, path: str):
        super().__init__(
            message=f"File not found: {path}",
            code="FILE_NOT_FOUND",
            severity=ErrorSeverity.FATAL,
            details={"path": path},
        )


class ExtractionError(DocMirrorError):
    """Extraction-related errors."""

    pass


class OCRExtractionError(ExtractionError):
    def __init__(self, confidence: float, threshold: float):
        super().__init__(
            message=f"OCR confidence {confidence:.2f} below threshold {threshold:.2f}",
            code="OCR_LOW_CONFIDENCE",
            severity=ErrorSeverity.DEGRADED,
            details={"confidence": confidence, "threshold": threshold},
            recoverable=True,  # Can retry with higher DPI
        )


class TableExtractionError(ExtractionError):
    def __init__(self, message: str, page: int = None):
        super().__init__(
            message=message,
            code="TABLE_EXTRACTION_FAILED",
            severity=ErrorSeverity.DEGRADED,
            details={"page": page},
            recoverable=True,
        )


class CacheError(DocMirrorError):
    """Cache-related errors."""

    def __init__(self, message: str):
        super().__init__(
            message=message,
            code="CACHE_ERROR",
            severity=ErrorSeverity.RECOVERABLE,
            recoverable=True,  # Can skip cache
        )


class ValidationError(DocMirrorError):
    """Validation-related errors."""

    def __init__(self, message: str, details: dict = None):
        super().__init__(
            message=message,
            code="VALIDATION_FAILED",
            severity=ErrorSeverity.DEGRADED,
            details=details or {},
            recoverable=False,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Result Type
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class Success(Generic[T]):
    """Represents a successful result."""

    value: T

    @property
    def is_success(self) -> bool:
        return True

    @property
    def is_failure(self) -> bool:
        return False

    def map(self, fn: Callable[[T], U]) -> Result[U, E]:
        """Transform the success value."""
        try:
            return Success(fn(self.value))
        except Exception as e:
            return Failure(
                DocMirrorError(
                    message=str(e),
                    code="MAP_ERROR",
                    severity=ErrorSeverity.FATAL,
                )
            )

    def and_then(self, fn: Callable[[T], Result[U, E]]) -> Result[U, E]:
        """Chain operations that return Result."""
        return fn(self.value)

    def or_else(self, _fn) -> Result[T, E]:
        """Return self (success case)."""
        return self

    def get_or_raise(self) -> T:
        """Get value or raise error."""
        return self.value

    def get_or_default(self, _default: U) -> T | U:
        """Get value or return default."""
        return self.value


@dataclass
class Failure(Generic[E]):
    """Represents a failed result."""

    error: E

    @property
    def is_success(self) -> bool:
        return False

    @property
    def is_failure(self) -> bool:
        return True

    def map(self, _fn) -> Result[U, E]:
        """Return self (failure case)."""
        return self

    def and_then(self, _fn) -> Result[U, E]:
        """Return self (failure case)."""
        return self

    def or_else(self, fn: Callable[[], Result[T, E]]) -> Result[T, E]:
        """Execute fallback function."""
        return fn()

    def get_or_raise(self) -> T:
        """Raise the error."""
        raise self.error

    def get_or_default(self, default: T) -> T:
        """Return default value."""
        return default


# Type alias
Result = Success[T] | Failure[E]


# ═══════════════════════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════════════════════


def success(value: T) -> Success[T]:
    """Create a Success result."""
    return Success(value)


def failure(error: E) -> Failure[E]:
    """Create a Failure result."""
    return Failure(error)


def try_catch(fn: Callable[[], T], error_factory: Callable[[Exception], E] = None) -> Result[T, E]:
    """
    Execute function and catch exceptions.

    Args:
        fn: Function to execute
        error_factory: Function to create error from exception

    Returns:
        Success with result or Failure with error
    """
    try:
        return Success(fn())
    except Exception as e:
        if error_factory:
            return Failure(error_factory(e))
        return Failure(
            DocMirrorError(
                message=str(e),
                code="UNEXPECTED_ERROR",
                severity=ErrorSeverity.FATAL,
            )
        )


async def try_catch_async(fn, error_factory=None) -> Result[T, E]:
    """Async version of try_catch."""
    try:
        result = await fn()
        return Success(result)
    except Exception as e:
        if error_factory:
            return Failure(error_factory(e))
        return Failure(
            DocMirrorError(
                message=str(e),
                code="UNEXPECTED_ERROR",
                severity=ErrorSeverity.FATAL,
            )
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Usage Examples
# ═══════════════════════════════════════════════════════════════════════════════

"""
Example 1: Basic usage

    result = divide(10, 2)
    if result.is_success:
        logger.debug(f"Result: {result.value}")
    else:
        logger.error(f"Error: {result.error}")

Example 2: Chaining operations

    result = (
        parse_file("doc.pdf")
        .and_then(extract_text)
        .and_then(parse_entities)
    )

    if result.is_success:
        entities = result.value
    else:
        handle_error(result.error)

Example 3: Fallback

    result = (
        get_from_cache(key)
        .or_else(lambda: fetch_from_database(key))
        .or_else(lambda: use_default_value())
    )

Example 4: Async usage

    result = await try_catch_async(
        lambda: cache.get(checksum),
        lambda e: CacheError(str(e))
    )

    if result.is_success:
        return result.value
    elif result.error.recoverable:
        logger.debug(f"Cache error (recoverable): {result.error}")
        return None
    else:
        raise result.error
"""
