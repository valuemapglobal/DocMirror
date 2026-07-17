# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Request-scoped parse control contract.

This module is the single normalization point for user-facing parse controls.
CLI, API, tests, and library callers should converge here before dispatching
work to adapters.
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
MirrorLevel = Literal["standard", "compact", "forensic"]
OutputFormat = Literal["json", "markdown", "csv", "chunks", "html", "parquet", "evidence"]
CachePolicy = Literal["read-write", "read-only", "refresh", "off"]
DocTypePolicy = Literal["prefer", "force"]
Edition = Literal["mirror", "community", "enterprise", "finance"]
GeometryLevel = Literal["none", "page", "block", "token", "full"]
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

_FORMAT_ALIASES = {
    "text": "markdown",
    "md": "markdown",
    "rag": "chunks",
    "rag_chunks": "chunks",
}
_STABLE_FORMATS: tuple[OutputFormat, ...] = ("json", "markdown", "csv", "chunks", "html", "parquet")
_AUX_FORMATS: tuple[OutputFormat, ...] = ("evidence",)
_VALID_FORMATS = frozenset((*_STABLE_FORMATS, *_AUX_FORMATS))
_VALID_MODES = frozenset(("auto", "fast", "balanced", "accurate", "forensic"))
_VALID_MIRROR_LEVELS = frozenset(("standard", "compact", "forensic"))
_VALID_CACHE_POLICIES = frozenset(("read-write", "read-only", "refresh", "off"))
_VALID_DOC_TYPE_POLICIES = frozenset(("prefer", "force"))
_STABLE_EDITIONS: tuple[Edition, ...] = ("mirror", "community", "enterprise", "finance")
_VALID_EDITIONS = frozenset(_STABLE_EDITIONS)
_VALID_GEOMETRY_LEVELS = frozenset(("none", "page", "block", "token", "full"))
_VALID_OCR_MODES = frozenset(("auto", "force", "off", "fallback"))
_VALID_OCR_CORRECTION_MODES = frozenset(("off", "safe", "suggest"))
_VALID_PAGE_SPLIT_MODES = frozenset(("auto", "off", "force"))
_VALID_SAFETY_MODES = frozenset(("off", "low", "medium", "high"))


def _default_editions() -> tuple[Edition, ...]:
    """License-aware default editions — SSOT via resolve_edition_tier()."""
    from docmirror.framework.edition_defaults import default_editions

    return default_editions()


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
class ResourceControl:
    """Total worker budget for this parse request."""

    workers: int | Literal["auto"] = "auto"
    page_executor: Literal["thread", "process", "auto"] = "auto"


@dataclass(frozen=True)
class OutputControl:
    """Requested output artifacts and mirror verbosity."""

    formats: tuple[OutputFormat, ...] = ("json",)
    editions: tuple[Edition, ...] = field(default_factory=_default_editions)
    mirror_level: MirrorLevel = "standard"
    geometry: GeometryLevel = "none"
    include_text: bool = False


@dataclass(frozen=True)
class DocTypeHint:
    """Human-provided document type prior."""

    value: str
    strength: Literal["prefer", "force"] = "prefer"
    source: Literal["user"] = "user"


@dataclass(frozen=True)
class ExecutionControl:
    """Execution policies that affect external side effects and pipeline choices."""

    cache_policy: CachePolicy = "read-write"
    ocr: OcrMode = "auto"
    ocr_correction: OcrCorrectionMode = "safe"
    ocr_language: str | None = None
    ocr_country: str | None = None
    ocr_locale: str | None = None
    ocr_correction_packs: tuple[str, ...] = ()
    page_split: PageSplitMode = "auto"


@dataclass(frozen=True)
class SafetyControl:
    """Safety inspection and sanitization controls (GA1.0-ODL-04)."""

    mode: SafetyMode = "medium"
    """Strictness level for AI safety inspection."""


@dataclass(frozen=True)
class ParseControl:
    """Single request-scoped parse control surface."""

    pages: PageSelection = field(default_factory=PageSelection)
    resource: ResourceControl = field(default_factory=ResourceControl)
    mode: ParseMode = "auto"
    execution: ExecutionControl = field(default_factory=ExecutionControl)
    output: OutputControl = field(default_factory=OutputControl)
    safety: SafetyControl = field(default_factory=SafetyControl)
    doc_type_hint: DocTypeHint | None = None
    skip_cache: bool = False
    mode_decision: dict[str, Any] = field(default_factory=dict)
    implicit_promotions: tuple[dict[str, str], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.doc_type_hint is None:
            data["doc_type_hint"] = None
        return data

    def fingerprint(self) -> str:
        """Stable fingerprint for result-affecting controls.

        Worker count is intentionally excluded: resource budget must not change
        deterministic output.
        """
        payload = {
            "pages": asdict(self.pages),
            "mode": self.mode,
            "execution": {
                "cache_policy": self.execution.cache_policy,
                "ocr": self.execution.ocr,
                "ocr_correction": self.execution.ocr_correction,
                "ocr_language": self.execution.ocr_language,
                "ocr_country": self.execution.ocr_country,
                "ocr_locale": self.execution.ocr_locale,
                "ocr_correction_packs": list(self.execution.ocr_correction_packs),
                "page_split": self.execution.page_split,
            },
            "safety": {
                "mode": self.safety.mode,
            },
            "output": {
                "formats": list(self.output.formats),
                "editions": list(self.output.editions),
                "mirror_level": self.output.mirror_level,
                "geometry": self.output.geometry,
                "include_text": self.output.include_text,
            },
            "doc_type_hint": asdict(self.doc_type_hint) if self.doc_type_hint else None,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    @property
    def enhance_mode(self) -> EnhanceMode:
        return mode_to_enhance_mode(self.mode)

    @property
    def cache_policy(self) -> CachePolicy:
        return self.execution.cache_policy


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


def parse_output_formats(raw: str | list[str] | tuple[str, ...] | None) -> tuple[OutputFormat, ...]:
    if raw is None:
        return ("json",)
    values: list[str] = []
    if isinstance(raw, str):
        values = [p.strip() for p in raw.split(",")]
    else:
        for item in raw:
            values.extend(str(item).split(","))
        values = [p.strip() for p in values]
    out: list[OutputFormat] = []
    for item in values:
        if not item:
            continue
        normalized = _FORMAT_ALIASES.get(item.lower(), item.lower())
        if normalized == "all":
            for fmt in _STABLE_FORMATS:
                if fmt not in out:
                    out.append(fmt)
            continue
        if normalized not in _VALID_FORMATS:
            raise ValueError(f"unsupported output format: {item}")
        if normalized not in out:
            out.append(normalized)  # type: ignore[arg-type]
    return tuple(out or ["json"])  # type: ignore[return-value]


def parse_editions(raw: str | list[str] | tuple[str, ...] | None) -> tuple[Edition, ...]:
    """Normalize explicitly requested delivery editions.

    The stable default is Community-only, while an explicit request is
    preserved as-is. The projection layer may still build Mirror internally.
    """
    if raw is None:
        return _default_editions()
    values: list[str] = []
    if isinstance(raw, str):
        values = [p.strip() for p in raw.split(",")]
    else:
        for item in raw:
            values.extend(str(item).split(","))
        values = [p.strip() for p in values]
    out: list[Edition] = []
    for item in values:
        if not item:
            continue
        normalized = item.lower()
        if normalized == "all":
            for edition in _STABLE_EDITIONS:
                if edition not in out:
                    out.append(edition)
            continue
        if normalized not in _VALID_EDITIONS:
            raise ValueError(f"unsupported edition: {item}")
        if normalized not in out:
            out.append(normalized)  # type: ignore[arg-type]
    if not out:
        return _default_editions()
    return tuple(out)  # type: ignore[return-value]


def parse_cache_policy(raw: str | None = None, *, skip_cache: bool | None = None) -> CachePolicy:
    if raw is not None:
        normalized = raw.strip().lower()
        if normalized not in _VALID_CACHE_POLICIES:
            raise ValueError(f"unsupported cache policy: {normalized}")
        return normalized  # type: ignore[return-value]
    if skip_cache is True:
        return "refresh"
    if skip_cache is False:
        return "read-write"
    return "read-write"


def parse_geometry(raw: str | None = None, *, include_geometry: bool | None = None) -> GeometryLevel:
    if include_geometry:
        return "full"
    normalized = (raw or "none").strip().lower()
    if normalized not in _VALID_GEOMETRY_LEVELS:
        raise ValueError(f"unsupported geometry level: {normalized}")
    return normalized  # type: ignore[return-value]


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


def parse_workers(raw: str | int | None) -> int | Literal["auto"]:
    if raw is None or raw == "":
        return "auto"
    if isinstance(raw, str) and raw.strip().lower() == "auto":
        return "auto"
    workers = int(raw)
    if workers < 1:
        raise ValueError("--workers must be >= 1 or auto")
    return workers


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


def mode_default_mirror_level(mode: str | None) -> MirrorLevel | None:
    normalized = (mode or "auto").strip().lower()
    try:
        from docmirror.configs.runtime.yaml_loader import config_loader

        configured = config_loader.get(f"parse.modes.{normalized}.mirror_level_default")
        if configured in _VALID_MIRROR_LEVELS:
            return configured  # type: ignore[return-value]
    except Exception:
        pass
    if normalized == "forensic":
        return "forensic"
    return None


def normalize_parse_control(
    control: ParseControl | None = None,
    *,
    pages: str | None = None,
    max_pages: int | None = None,
    workers: str | int | None = None,
    mode: str | None = None,
    formats: str | list[str] | tuple[str, ...] | None = None,
    editions: str | list[str] | tuple[str, ...] | None = None,
    mirror_level: str | None = None,
    geometry: str | None = None,
    include_geometry: bool | None = None,
    include_text: bool | None = None,
    doc_type: str | None = None,
    doc_type_policy: str | None = None,
    doc_type_hint: str | None = None,
    cache_policy: str | None = None,
    skip_cache: bool | None = None,
    ocr: str | None = None,
    ocr_correction: str | None = None,
    ocr_language: str | None = None,
    ocr_country: str | None = None,
    ocr_locale: str | None = None,
    ocr_correction_packs: str | list[str] | tuple[str, ...] | None = None,
    page_split: str | None = None,
    enhance_mode: str | None = None,
) -> ParseControl:
    """Return a normalized ParseControl with explicit args applied."""
    base = control or ParseControl()
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

    resource = base.resource
    if workers is not None:
        resource = ResourceControl(workers=parse_workers(workers), page_executor=resource.page_executor)

    resolved_cache_policy = base.execution.cache_policy
    if cache_policy is not None:
        resolved_cache_policy = parse_cache_policy(cache_policy)
    elif skip_cache is not None:
        resolved_cache_policy = parse_cache_policy(skip_cache=bool(skip_cache))

    from docmirror.ocr.correction.language import resolve_language_hint

    locale_input = (
        ocr_locale
        if ocr_locale is not None
        else (None if ocr_language is not None or ocr_country is not None else base.execution.ocr_locale)
    )
    language_context = resolve_language_hint(
        "",
        language=(
            ocr_language
            if ocr_language is not None
            else (None if ocr_locale is not None else base.execution.ocr_language)
        ),
        country=(
            ocr_country if ocr_country is not None else (None if ocr_locale is not None else base.execution.ocr_country)
        ),
        locale=locale_input,
    )
    execution = ExecutionControl(
        cache_policy=resolved_cache_policy,
        ocr=parse_ocr_mode(ocr) if ocr is not None else base.execution.ocr,
        ocr_correction=(
            parse_ocr_correction_mode(ocr_correction) if ocr_correction is not None else base.execution.ocr_correction
        ),
        ocr_language=language_context.language,
        ocr_country=language_context.country,
        ocr_locale=language_context.locale,
        ocr_correction_packs=(
            parse_ocr_correction_packs(ocr_correction_packs)
            if ocr_correction_packs is not None
            else base.execution.ocr_correction_packs
        ),
        page_split=parse_page_split_mode(page_split) if page_split is not None else base.execution.page_split,
    )

    output = base.output
    resolved_editions = parse_editions(editions)
    if (
        formats is not None
        or editions is not None
        or mirror_level is not None
        or geometry is not None
        or include_geometry is not None
        or include_text is not None
    ):
        resolved_formats = parse_output_formats(formats) if formats is not None else output.formats
        resolved_mirror = (mirror_level or output.mirror_level).strip().lower()
        if resolved_mirror not in _VALID_MIRROR_LEVELS:
            raise ValueError(f"unsupported mirror level: {resolved_mirror}")
        resolved_geometry = (
            parse_geometry(geometry, include_geometry=include_geometry)
            if geometry is not None or include_geometry is not None
            else output.geometry
        )
        output = OutputControl(
            formats=resolved_formats,
            editions=resolved_editions,
            mirror_level=resolved_mirror,  # type: ignore[arg-type]
            geometry=resolved_geometry,
            include_text=output.include_text if include_text is None else bool(include_text),
        )

    elif resolved_editions != output.editions:
        output = OutputControl(
            formats=output.formats,
            editions=resolved_editions,
            mirror_level=output.mirror_level,
            geometry=output.geometry,
            include_text=output.include_text,
        )
    if doc_type is not None:
        hint = parse_doc_type(doc_type, doc_type_policy)
    elif doc_type_hint is not None:
        hint = parse_doc_type_hint(doc_type_hint)
    else:
        hint = base.doc_type_hint

    implicit_promotions = list(base.implicit_promotions)
    default_mirror = mode_default_mirror_level(resolved_mode)
    if default_mirror and output.mirror_level != default_mirror and mirror_level is None:
        output = OutputControl(
            formats=output.formats,
            editions=output.editions,
            mirror_level=default_mirror,
            geometry=output.geometry,
            include_text=output.include_text,
        )
        implicit_promotions.append(
            {
                "from": f"mode={resolved_mode}",
                "to": f"mirror_level={default_mirror}",
                "reason": f"{resolved_mode} mode requires {default_mirror} output by default",
            }
        )
    if output.geometry == "full" and output.mirror_level != "forensic":
        output = OutputControl(
            formats=output.formats,
            editions=output.editions,
            mirror_level="forensic",
            geometry=output.geometry,
            include_text=output.include_text,
        )
        implicit_promotions.append(
            {
                "from": "geometry=full",
                "to": "mirror_level=forensic",
                "reason": "full geometry requires forensic mirror output",
            }
        )

    return ParseControl(
        pages=page_selection,
        resource=resource,
        mode=resolved_mode,  # type: ignore[arg-type]
        execution=execution,
        safety=base.safety,
        output=output,
        doc_type_hint=hint,
        skip_cache=execution.cache_policy in {"refresh", "off"},
        mode_decision={
            "requested": resolved_mode,
            "resolved_enhance_mode": mode_to_enhance_mode(resolved_mode),
            "resolved_profile": "balanced" if resolved_mode == "auto" else resolved_mode,
            "reason": "auto defaults to balanced until pre-analysis dynamic routing is enabled"
            if resolved_mode == "auto"
            else "explicit mode",
        },
        implicit_promotions=tuple(implicit_promotions),
    )


__all__ = [
    "DocTypeHint",
    "ExecutionControl",
    "OutputControl",
    "PageSelection",
    "ParseControl",
    "ResourceControl",
    "parse_cache_policy",
    "parse_doc_type",
    "mode_to_enhance_mode",
    "mode_default_mirror_level",
    "normalize_parse_control",
    "parse_doc_type_hint",
    "parse_editions",
    "parse_geometry",
    "parse_ocr_correction_mode",
    "parse_ocr_correction_packs",
    "parse_ocr_mode",
    "parse_output_formats",
    "parse_page_split_mode",
    "parse_page_selection",
    "parse_workers",
]
