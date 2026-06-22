"""
Output Profile Registry — defines artifact sets for GA profiles.

GA 1.0 design: §6 Output Coverage — `ga_full` generates a complete artifact pack
for human, system, and audit consumers from one parse.

Usage::
    from docmirror.configs.output_profile import resolve_profile
    artifacts = resolve_profile("ga_full")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import yaml

from docmirror.configs.paths import GA_READINESS_YAML


@dataclass(frozen=True)
class OutputProfile:
    """Defines which artifacts a profile generates."""

    name: str
    label: str = ""
    mirror: bool = True
    community: bool = True
    enterprise: bool = True
    finance: bool = True
    markdown: bool = True
    evidence_bundle: bool = True
    quality_report: bool = True
    visual_debug: bool = True
    manifest: bool = True
    description: str = ""
    is_default: bool = False

    @property
    def editions(self) -> tuple[str, ...]:
        """The edition names this profile should generate."""
        chosen: list[str] = ["mirror"]
        if self.community:
            chosen.append("community")
        if self.enterprise:
            chosen.append("enterprise")
        if self.finance:
            chosen.append("finance")
        return tuple(chosen)

    @property
    def formats(self) -> tuple[str, ...]:
        """Extra export formats this profile should produce."""
        fmts: list[str] = []
        if self.markdown:
            fmts.append("markdown")
        if self.evidence_bundle:
            fmts.append("evidence")
        return tuple(fmts)


# ── Built-in profiles ─────────────────────────────────────────────────────

GA_FULL = OutputProfile(
    name="ga_full",
    label="GA Full Output",
    mirror=True,
    community=True,
    enterprise=True,
    finance=True,
    markdown=True,
    evidence_bundle=True,
    quality_report=True,
    visual_debug=True,
    manifest=True,
    description="GA 1.0 full artifact pack: mirror, editions, markdown, evidence, quality, visual debug, manifest",
    is_default=False,
)

LEGACY_JSON = OutputProfile(
    name="legacy_json",
    label="Legacy JSON",
    mirror=True,
    community=True,
    enterprise=True,
    finance=True,
    markdown=False,
    evidence_bundle=False,
    quality_report=False,
    visual_debug=False,
    manifest=False,
    description="Pre-GA behavior: mirror + edition JSON only",
    is_default=False,
)

QUICKSTART = OutputProfile(
    name="quickstart",
    label="Quickstart",
    mirror=True,
    community=True,
    enterprise=True,
    finance=True,
    markdown=True,
    evidence_bundle=True,
    quality_report=True,
    visual_debug=True,
    manifest=True,
    description="Quickstart artifact pack (mirror, edition, markdown, evidence, visual debug, manifest)",
    is_default=False,
)


COMPACT = OutputProfile(
    name="compact",
    label="Compact",
    mirror=True,
    community=False,
    enterprise=False,
    finance=False,
    markdown=True,
    evidence_bundle=False,
    quality_report=False,
    visual_debug=False,
    manifest=False,
    description="Mirror + Markdown only (no edition, no evidence bundle)",
    is_default=False,
)

FULL = OutputProfile(
    name="full",
    label="Full (GA Default)",
    mirror=True,
    community=True,
    enterprise=True,
    finance=True,
    markdown=True,
    evidence_bundle=True,
    quality_report=True,
    visual_debug=True,
    manifest=True,
    description="GA 1.0 default: mirror, editions, markdown, evidence, quality, visual debug, manifest",
    is_default=False,
)

DEFAULT = OutputProfile(
    name="default",
    label="Default (GA Transition)",
    mirror=True,
    community=True,
    enterprise=False,
    finance=False,
    markdown=False,
    evidence_bundle=False,
    quality_report=False,
    visual_debug=False,
    manifest=False,
    description="Default for open-source users: mirror + community JSON. Enterprise, finance, markdown, manifest, evidence require --profile ga_full.",
    is_default=True,
)

FORENSIC = OutputProfile(
    name="forensic",
    label="Forensic",
    mirror=True,
    community=True,
    enterprise=True,
    finance=True,
    markdown=True,
    evidence_bundle=True,
    quality_report=True,
    visual_debug=True,
    manifest=True,
    description="Forensic archive: ga_full + noise preservation + full bbox + full DFG",
    is_default=False,
)

# ── Registry ────────────────────────────────────────────────────────────

_PROFILES: dict[str, OutputProfile] = {
    "compact": COMPACT,
    "full": FULL,
    "default": DEFAULT,
    "ga_full": GA_FULL,
    "forensic": FORENSIC,
    "legacy_json": LEGACY_JSON,
    "quickstart": QUICKSTART,
}


def resolve_profile(name: str) -> OutputProfile:
    """Resolve a profile name to its definition."""
    normalized = name.lower().strip()
    if normalized in _PROFILES:
        return _PROFILES[normalized]
    raise ValueError(
        f"Unknown output profile: {name!r}. Available: {sorted(_PROFILES)}"
    )


def default_profile() -> OutputProfile:
    """Return the default profile for the current environment."""
    return DEFAULT


def list_profiles() -> tuple[str, ...]:
    """Return all known profile names."""
    return tuple(_PROFILES)


__all__ = [
    "OutputProfile",
    "GA_FULL",
    "LEGACY_JSON",
    "QUICKSTART",
    "resolve_profile",
    "default_profile",
    "list_profiles",
]
