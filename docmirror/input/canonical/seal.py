# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Final canonical validation and mutation-audit gate before sealing."""

from __future__ import annotations

from docmirror.models.entities.parse_result import ParseResult
from docmirror.models.sealed import SealedParseResult, seal_parse_result


class CanonicalValidationError(ValueError):
    """Raised when the fact model is not safe to seal."""


def validate_canonical_result(result: ParseResult) -> ParseResult:
    """Validate model integrity and required mutation-audit attribution."""
    if not isinstance(result, ParseResult):
        raise TypeError(f"validate_canonical_result expects ParseResult; got {type(result).__name__}")
    # A complete Pydantic round trip catches invalid nested assignments made by
    # mutable middleware before the immutable boundary is crossed.
    validated = ParseResult.model_validate(result.model_dump(mode="python", exclude_none=False))
    for index, mutation in enumerate(validated.mutations):
        if not str(mutation.middleware_name or "").strip():
            raise CanonicalValidationError(f"mutation[{index}] has no actor")
        if not str(mutation.field_changed or "").strip():
            raise CanonicalValidationError(f"mutation[{index}] has no target field")
        if not str(mutation.reason or "").strip():
            raise CanonicalValidationError(f"mutation[{index}] has no reason")
    return validated


def seal_canonical_result(result: ParseResult) -> SealedParseResult:
    """Run the final validation/audit gate and create the immutable snapshot."""
    return seal_parse_result(validate_canonical_result(result))


__all__ = ["CanonicalValidationError", "seal_canonical_result", "validate_canonical_result"]
