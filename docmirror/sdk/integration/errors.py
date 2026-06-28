"""Unified ErrorEnvelope for CLI, SDK, REST, Docker, and task surfaces.

Every failure produced by DocMirror — whether caught in-process, returned
by the REST layer, or persisted in a task result — must use this envelope
shape so callers can handle errors with a single code path.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class ErrorEnvelope:
    """Stable error shape consumed by all DocMirror integration surfaces.

    Contract invariants:
        * ``code`` is a stable machine-readable identifier.
        * ``recoverable`` tells the caller whether a retry is safe.
        * ``suggestion`` is human-readable guidance.
        * ``docs_url`` points to the canonical help page for this error.
        * ``details`` is an open bag for surface-specific metadata.
    """

    code: str                                    # e.g. UNSUPPORTED_FORMAT
    message: str = ""
    recoverable: bool = False
    suggestion: str = ""
    docs_url: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    request_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None and v != {} and v != ""}

    @classmethod
    def from_exception(cls, exc: Exception, request_id: str | None = None) -> ErrorEnvelope:
        """Build a fallback envelope from an unhandled exception."""
        return cls(
            code="INTERNAL_ERROR",
            message=str(exc)[:500],
            recoverable=False,
            suggestion="Please open an issue at https://github.com/valuemapglobal/docmirror/issues",
            docs_url="https://docs.docmirror.com/troubleshooting/internal-error",
            request_id=request_id,
        )

    @classmethod
    def for_unsupported_format(cls, fmt: str, request_id: str | None = None) -> ErrorEnvelope:
        return cls(
            code="UNSUPPORTED_FORMAT",
            message=f"Format '{fmt}' is not currently supported.",
            recoverable=False,
            suggestion="Try converting to PDF or check the supported format registry.",
            docs_url="https://docs.docmirror.com/reference/supported-formats",
            request_id=request_id,
        )

    @classmethod
    def for_timeout(cls, timeout_s: float, request_id: str | None = None) -> ErrorEnvelope:
        return cls(
            code="TIMEOUT",
            message=f"Request timed out after {timeout_s:.0f}s.",
            recoverable=True,
            suggestion="Retry with a longer timeout or reduce document complexity.",
            docs_url="https://docs.docmirror.com/troubleshooting/timeout",
            request_id=request_id,
        )


class DocMirrorError(Exception):
    """Base exception for DocMirror SDK errors.

    Wraps an ``ErrorEnvelope`` so callers can capture a stable machine-readable
    error via ``except DocMirrorError as e: print(e.envelope.code)``.
    """

    def __init__(self, envelope: ErrorEnvelope):
        super().__init__(envelope.message)
        self.envelope = envelope

    @classmethod
    def from_envelope(cls, envelope: ErrorEnvelope) -> DocMirrorError:
        """Construct from an ErrorEnvelope."""
        return cls(envelope)


def raise_on_error(
    result_or_errors: Any,
    raise_exc: bool = True,
) -> None:
    """Conditionally raise ``DocMirrorError`` from task result errors."""
    if not raise_exc:
        return
    errors: list[Any] = []
    if isinstance(result_or_errors, list):
        errors = result_or_errors
    elif hasattr(result_or_errors, "errors"):
        errors = result_or_errors.errors or []
    elif isinstance(result_or_errors, dict):
        errors = result_or_errors.get("errors") or []
    if errors:
        first = errors[0]
        if isinstance(first, ErrorEnvelope):
            raise DocMirrorError(first)
        if isinstance(first, dict):
            envelope = ErrorEnvelope(**first)
            raise DocMirrorError(envelope)
