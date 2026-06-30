"""FailureCodeRegistry loader — reads failure_codes.yaml and provides typed lookups.

Part of the Failure & Degradation Contract (FDC). All public surfaces share the
same canonical/user code mappings, severity, recoverability, and suggestions.

Usage::

    from docmirror.configs.failure_codes import (
        FailureCodeRegistry,
        FailureCodeEntry,
        registry,
    )
    entry = registry.lookup("unsupported_format")
    assert entry.canonical_code == "UNSUPPORTED_FORMAT"
    assert entry.recoverable is False
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class FailureCodeEntry:
    """Typed view of a single registered failure code."""

    canonical_code: str
    user_code: str
    category: str
    default_scope: str
    severity: str
    recoverable: bool
    retryable: bool
    default_message: str
    default_suggestion: str
    docs_anchor: str
    public: bool = True
    extra: dict[str, Any] = field(default_factory=dict)


class FailureCodeRegistry:
    """Immutable registry of all canonical failure/degradation codes.

    Backed by ``configs/yaml/failure_codes.yaml``. Thread-safe after first load.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_canonical: dict[str, FailureCodeEntry] = {}
        self._by_user: dict[str, FailureCodeEntry] = {}
        self._loaded = False

    # ── loading ──────────────────────────────────────────────────

    def load(self) -> None:
        """Load registry from YAML (idempotent, thread-safe)."""
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self._load_impl()
            self._loaded = True

    def _load_impl(self) -> None:
        import yaml

        yaml_path = Path(__file__).resolve().parent / "yaml" / "failure_codes.yaml"
        if not yaml_path.exists():
            raise FileNotFoundError(f"Failure code registry YAML not found: {yaml_path}")

        raw: dict[str, dict[str, Any]] = yaml.safe_load(yaml_path.read_text("utf-8")) or {}

        for _key, entry_dict in raw.items():
            fc = FailureCodeEntry(
                canonical_code=entry_dict.get("canonical_code", ""),
                user_code=entry_dict.get("user_code", ""),
                category=entry_dict.get("category", "parse"),
                default_scope=entry_dict.get("default_scope", "document"),
                severity=entry_dict.get("severity", "error"),
                recoverable=bool(entry_dict.get("recoverable", False)),
                retryable=bool(entry_dict.get("retryable", False)),
                default_message=entry_dict.get("default_message", ""),
                default_suggestion=entry_dict.get("default_suggestion", ""),
                docs_anchor=entry_dict.get("docs_anchor", ""),
                public=bool(entry_dict.get("public", True)),
            )
            self._by_canonical[fc.canonical_code] = fc
            self._by_user[fc.user_code] = fc

    # ── lookup ───────────────────────────────────────────────────

    def lookup(self, code: str) -> FailureCodeEntry | None:
        """Look up by user_code (lower_snake_case) or canonical_code (UPPER_SNAKE_CASE).

        Returns None when the code is not registered.
        """
        self._ensure_loaded()
        return self._by_user.get(code) or self._by_canonical.get(code)

    def lookup_canonical(self, canonical: str) -> FailureCodeEntry | None:
        """Look up strictly by canonical_code."""
        self._ensure_loaded()
        return self._by_canonical.get(canonical)

    def lookup_user(self, user_code: str) -> FailureCodeEntry | None:
        """Look up strictly by user_code."""
        self._ensure_loaded()
        return self._by_user.get(user_code)

    def list_public(self) -> list[FailureCodeEntry]:
        """Return all public (user-visible) registered codes."""
        self._ensure_loaded()
        return [e for e in self._by_user.values() if e.public]

    def list_all(self) -> list[FailureCodeEntry]:
        """Return every registered code."""
        self._ensure_loaded()
        return list(self._by_canonical.values())

    def list_by_category(self, category: str) -> list[FailureCodeEntry]:
        """Return codes filtered by category."""
        self._ensure_loaded()
        return [e for e in self._by_canonical.values() if e.category == category]

    # ── helpers ──────────────────────────────────────────────────

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def is_registered(self, canonical_code: str) -> bool:
        """True if canonical_code exists in registry."""
        self._ensure_loaded()
        return canonical_code in self._by_canonical

    def user_to_canonical(self, user_code: str) -> str:
        """Map user_code to canonical_code. Returns empty string if unknown."""
        entry = self.lookup_user(user_code)
        return entry.canonical_code if entry else ""

    def canonical_to_user(self, canonical_code: str) -> str:
        """Map canonical_code to user_code. Returns empty string if unknown."""
        entry = self.lookup_canonical(canonical_code)
        return entry.user_code if entry else ""


# Module-level singleton — import and call registry.load() or just use registry.lookup()
registry = FailureCodeRegistry()


# ── convenience helpers ───────────────────────────────────────────


def get_error_entry(code: str) -> FailureCodeEntry | None:
    """Convenience: look up a code with auto-load."""
    return registry.lookup(code)


def build_error_envelope_from_code(
    user_code: str,
    *,
    message: str = "",
    details: dict[str, Any] | None = None,
    scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a canonical error envelope dict from a registered user_code.

    Used by REST error handlers, SDK exceptions, and CLI output layers
    to produce consistent error shapes without duplicating metadata.
    """
    entry = registry.lookup(user_code)
    if entry is None:
        # Fallback for unregistered codes — mark as internal
        return {
            "code": user_code,
            "canonical_code": user_code.upper(),
            "message": message or "An unexpected error occurred.",
            "scope": scope or {"type": "unknown"},
            "recoverable": False,
            "retryable": False,
            "suggestion": "Submit a support bundle for investigation.",
            "docs_anchor": "troubleshooting",
            "details": details or {},
        }

    return {
        "code": entry.user_code,
        "canonical_code": entry.canonical_code,
        "message": message or entry.default_message,
        "scope": scope or {"type": entry.default_scope},
        "recoverable": entry.recoverable,
        "retryable": entry.retryable,
        "suggestion": entry.default_suggestion,
        "docs_anchor": entry.docs_anchor,
        "details": details or {},
    }
