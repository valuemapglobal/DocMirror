# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Canonical fact policy for document parsing.

Only options that may change ``ParseResult`` facts belong here. Delivery,
caching, resource limits, and progress reporting are intentionally absent.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

EnhanceMode = Literal["raw", "standard", "full"]
ParseMode = Literal["auto", "fast", "balanced", "accurate", "forensic"]
DocTypePolicy = Literal["prefer", "force"]
OcrMode = Literal["auto", "force", "off", "fallback"]
OcrCorrectionMode = Literal["off", "safe", "suggest"]
PageSplitMode = Literal["auto", "off", "force"]
SafetyMode = Literal["off", "low", "medium", "high"]
"""Safety inspection strictness for AI pipeline defense.

- off: No safety inspection (pass-through, stable API behavior).
- low: Detect only — report findings, no auto-sanitize.
- medium: Remove zero-width chars + flag hidden text (default).
- high: Remove hidden text + zero-width chars + flag injections.
"""

_VALID_MODES = frozenset(("auto", "fast", "balanced", "accurate", "forensic"))
_VALID_DOC_TYPE_POLICIES = frozenset(("prefer", "force"))
_VALID_OCR_MODES = frozenset(("auto", "force", "off", "fallback"))
_VALID_OCR_CORRECTION_MODES = frozenset(("off", "safe", "suggest"))
_VALID_PAGE_SPLIT_MODES = frozenset(("auto", "off", "force"))
_VALID_SAFETY_MODES = frozenset(("off", "low", "medium", "high"))


@dataclass(frozen=True)
class PageSelection:
    """Page selection expressed in 1-based user-facing ranges."""

    ranges: tuple[tuple[int, int | None], ...] = ()
    max_pages: int | None = None
    last_pages: int | None = None

    @property
    def is_all_pages(self) -> bool:
        return not self.ranges and self.max_pages is None and self.last_pages is None

    def resolve(self, total_pages: int) -> list[int]:
        """Resolve to sorted 0-based page indices for a document."""
        if total_pages <= 0:
            return []
        if self.last_pages is not None:
            start = max(0, total_pages - int(self.last_pages))
            selected = list(range(start, total_pages))
        elif not self.ranges:
            selected = list(range(total_pages))
        else:
            seen: set[int] = set()
            selected = []
            for start, end in self.ranges:
                start_1 = max(1, int(start))
                end_1 = total_pages if end is None else min(total_pages, int(end))
                if end_1 < start_1:
                    continue
                for page_no in range(start_1, end_1 + 1):
                    idx = page_no - 1
                    if idx not in seen:
                        seen.add(idx)
                        selected.append(idx)
        if self.max_pages is not None:
            selected = selected[: max(0, int(self.max_pages))]
        return selected

    def to_display(self) -> str:
        if not self.ranges:
            if self.last_pages is not None:
                return f"last:{self.last_pages}"
            return f"first:{self.max_pages}" if self.max_pages is not None else "all"
        parts = []
        for start, end in self.ranges:
            parts.append(f"{start}-" if end is None else (str(start) if start == end else f"{start}-{end}"))
        expr = ",".join(parts)
        if self.max_pages is not None:
            expr = f"{expr} (max {self.max_pages})"
        return expr


@dataclass(frozen=True)
class DocTypeHint:
    """Human-provided document type prior."""

    value: str
    strength: Literal["prefer", "force"] = "prefer"
    source: Literal["user"] = "user"


@dataclass(frozen=True)
class SafetyControl:
    """Safety inspection and sanitization controls (GA1.0-ODL-04)."""

    mode: SafetyMode = "medium"
    """Strictness level for AI safety inspection."""


@dataclass(frozen=True)
class ParsePolicy:
    """Fact-affecting parse policy passed to Dispatcher and adapters."""

    pages: PageSelection = field(default_factory=PageSelection)
    mode: ParseMode = "auto"
    ocr: OcrMode = "auto"
    ocr_correction: OcrCorrectionMode = "safe"
    ocr_language: str | None = None
    ocr_country: str | None = None
    ocr_locale: str | None = None
    ocr_correction_packs: tuple[str, ...] = ()
    page_split: PageSplitMode = "auto"
    safety: SafetyControl = field(default_factory=SafetyControl)
    doc_type_hint: DocTypeHint | None = None
    mode_decision: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def enhance_mode(self) -> EnhanceMode:
        return mode_to_enhance_mode(self.mode)

    def fingerprint(self) -> str:
        """Stable fingerprint containing fact-affecting options only."""
        payload = {
            "pages": asdict(self.pages),
            "mode": self.mode,
            "ocr": self.ocr,
            "ocr_correction": self.ocr_correction,
            "ocr_language": self.ocr_language,
            "ocr_country": self.ocr_country,
            "ocr_locale": self.ocr_locale,
            "ocr_correction_packs": list(self.ocr_correction_packs),
            "page_split": self.page_split,
            "safety": asdict(self.safety),
            "doc_type_hint": asdict(self.doc_type_hint) if self.doc_type_hint else None,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def parse_page_selection(pages: str | None = None, max_pages: int | None = None) -> PageSelection:
    """Parse CLI/API page range text into a PageSelection."""
    ranges: list[tuple[int, int | None]] = []
    expr = (pages or "").strip().lower()
    if expr:
        if expr.startswith("first:"):
            max_pages = int(expr.split(":", 1)[1])
        elif expr.startswith("last:"):
            last_pages = int(expr.split(":", 1)[1])
            if last_pages < 0:
                raise ValueError("--pages last:N requires N >= 0")
            return PageSelection((), int(max_pages) if max_pages is not None else None, last_pages)
        else:
            for part in expr.split(","):
                token = part.strip()
                if not token:
                    continue
                if "-" in token:
                    left, right = token.split("-", 1)
                    if not left.strip():
                        raise ValueError(f"invalid page range: {token!r}")
                    start = int(left)
                    end = int(right) if right.strip() else None
                    if end is not None and end < start:
                        raise ValueError(f"invalid descending page range: {token!r}")
                    ranges.append((start, end))
                else:
                    page = int(token)
                    ranges.append((page, page))
    if max_pages is not None and int(max_pages) < 0:
        raise ValueError("--max-pages must be >= 0")
    return PageSelection(tuple(ranges), int(max_pages) if max_pages is not None else None)


def parse_doc_type_hint(raw: str | None) -> DocTypeHint | None:
    val = (raw or "").strip()
    if not val:
        return None
    if ":" in val:
        value, strength = val.split(":", 1)
        strength = strength.strip().lower()
    else:
        value, strength = val, "prefer"
    value = value.strip()
    if not value:
        return None
    if strength not in {"prefer", "force"}:
        raise ValueError("--doc-type-hint strength must be prefer or force")
    return DocTypeHint(value=value, strength=strength)  # type: ignore[arg-type]


def parse_doc_type(value: str | None, policy: str | None = None) -> DocTypeHint | None:
    doc_type = (value or "").strip()
    if not doc_type:
        return None
    resolved_policy = (policy or "prefer").strip().lower()
    if resolved_policy not in _VALID_DOC_TYPE_POLICIES:
        raise ValueError("--doc-type-policy must be prefer or force")
    return DocTypeHint(value=doc_type, strength=resolved_policy)  # type: ignore[arg-type]


def parse_ocr_mode(raw: str | None = None) -> OcrMode:
    normalized = (raw or "auto").strip().lower()
    if normalized not in _VALID_OCR_MODES:
        raise ValueError(f"unsupported OCR mode: {normalized}")
    return normalized  # type: ignore[return-value]


def parse_ocr_correction_mode(raw: str | None = None) -> OcrCorrectionMode:
    normalized = (raw or "safe").strip().lower()
    if normalized not in _VALID_OCR_CORRECTION_MODES:
        raise ValueError(f"unsupported OCR correction mode: {normalized}")
    return normalized  # type: ignore[return-value]


def parse_ocr_correction_packs(raw: str | list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    if raw is None:
        return ()
    values = [raw] if isinstance(raw, str) else list(raw)
    out: list[str] = []
    for value in values:
        for item in str(value).split(","):
            pack_id = item.strip()
            if not pack_id:
                continue
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", pack_id):
                raise ValueError(f"invalid OCR correction pack id: {pack_id!r}")
            if pack_id not in out:
                out.append(pack_id)
    return tuple(out)


def parse_page_split_mode(raw: str | None = None) -> PageSplitMode:
    normalized = (raw or "auto").strip().lower()
    if normalized not in _VALID_PAGE_SPLIT_MODES:
        raise ValueError(f"unsupported page split mode: {normalized}")
    return normalized  # type: ignore[return-value]


def mode_to_enhance_mode(mode: str | None) -> EnhanceMode:
    normalized = (mode or "auto").strip().lower()
    try:
        from docmirror.configs.runtime.yaml_loader import config_loader

        configured = config_loader.get(f"parse.modes.{normalized}.enhance_mode")
        if configured in {"raw", "standard", "full"}:
            return configured
    except Exception:
        pass
    if normalized == "fast":
        return "raw"
    if normalized in {"accurate", "forensic"}:
        return "full"
    return "standard"


def normalize_parse_policy(
    policy: ParsePolicy | None = None,
    *,
    pages: str | None = None,
    max_pages: int | None = None,
    mode: str | None = None,
    doc_type: str | None = None,
    doc_type_policy: str | None = None,
    doc_type_hint: str | None = None,
    ocr: str | None = None,
    ocr_correction: str | None = None,
    ocr_language: str | None = None,
    ocr_country: str | None = None,
    ocr_locale: str | None = None,
    ocr_correction_packs: str | list[str] | tuple[str, ...] | None = None,
    page_split: str | None = None,
    enhance_mode: str | None = None,
) -> ParsePolicy:
    """Return one normalized policy containing fact-affecting options only."""
    base = policy or ParsePolicy()
    resolved_mode = (mode or base.mode or "auto").strip().lower()
    if enhance_mode and not mode:
        enhance = enhance_mode.strip().lower()
        if enhance == "raw":
            resolved_mode = "fast"
        elif enhance == "full":
            resolved_mode = "accurate"
        elif enhance == "standard" and base.mode == "auto":
            resolved_mode = "balanced"
    if resolved_mode not in _VALID_MODES:
        raise ValueError(f"unsupported parse mode: {resolved_mode}")

    if pages is not None or max_pages is not None:
        page_selection = parse_page_selection(pages, max_pages)
    else:
        page_selection = base.pages
        env_max_pages = os.environ.get("DOCMIRROR_MAX_PAGES", "").strip()
        if page_selection.max_pages is None and env_max_pages.isdigit():
            page_selection = PageSelection(page_selection.ranges, int(env_max_pages))

    from docmirror.ocr.correction.language import resolve_language_hint

    locale_input = (
        ocr_locale
        if ocr_locale is not None
        else (None if ocr_language is not None or ocr_country is not None else base.ocr_locale)
    )
    language_context = resolve_language_hint(
        "",
        language=(
            ocr_language if ocr_language is not None else (None if ocr_locale is not None else base.ocr_language)
        ),
        country=(ocr_country if ocr_country is not None else (None if ocr_locale is not None else base.ocr_country)),
        locale=locale_input,
    )
    if doc_type is not None:
        hint = parse_doc_type(doc_type, doc_type_policy)
    elif doc_type_hint is not None:
        hint = parse_doc_type_hint(doc_type_hint)
    else:
        hint = base.doc_type_hint

    return ParsePolicy(
        pages=page_selection,
        mode=resolved_mode,  # type: ignore[arg-type]
        ocr=parse_ocr_mode(ocr) if ocr is not None else base.ocr,
        ocr_correction=(
            parse_ocr_correction_mode(ocr_correction) if ocr_correction is not None else base.ocr_correction
        ),
        ocr_language=language_context.language,
        ocr_country=language_context.country,
        ocr_locale=language_context.locale,
        ocr_correction_packs=(
            parse_ocr_correction_packs(ocr_correction_packs)
            if ocr_correction_packs is not None
            else base.ocr_correction_packs
        ),
        page_split=parse_page_split_mode(page_split) if page_split is not None else base.page_split,
        safety=base.safety,
        doc_type_hint=hint,
        mode_decision={
            "requested": resolved_mode,
            "resolved_enhance_mode": mode_to_enhance_mode(resolved_mode),
            "resolved_profile": "balanced" if resolved_mode == "auto" else resolved_mode,
            "reason": "auto defaults to balanced until pre-analysis dynamic routing is enabled"
            if resolved_mode == "auto"
            else "explicit mode",
        },
    )


__all__ = [
    "DocTypeHint",
    "PageSelection",
    "ParsePolicy",
    "parse_doc_type",
    "mode_to_enhance_mode",
    "normalize_parse_policy",
    "parse_doc_type_hint",
    "parse_ocr_correction_mode",
    "parse_ocr_correction_packs",
    "parse_ocr_mode",
    "parse_page_split_mode",
    "parse_page_selection",
]
