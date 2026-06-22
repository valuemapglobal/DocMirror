"""
Output Profile SSOT — unified profile enumeration for CLI, API, and internal routing.

GA 1.0 design §2.1 Convergence 1: Profile is the user's single declaration of
computation depth and output scope. CLI, API, and internal routing all derive
from this single source of truth.

Usage::
    from docmirror.models.entities.output_profile import OutputProfile, PROFILE_ROUTING
    routing = PROFILE_ROUTING[OutputProfile.GA_FULL]
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class OutputProfile(str, Enum):
    """Unified output profile — single SSOT for CLI, API, and internal routing.

    Profiles are ordered by increasing computation depth and output scope:
    compact < full < ga_full < forensic.
    """

    COMPACT = "compact"
    FULL = "full"
    GA_FULL = "ga_full"
    FORENSIC = "forensic"

    @classmethod
    def from_string(cls, value: str | None) -> OutputProfile:
        """Parse a profile string, defaulting to FULL."""
        if not value:
            return cls.FULL
        normalized = value.lower().strip()
        for member in cls:
            if member.value == normalized:
                return member
        # Legacy aliases
        if normalized in ("quickstart",):
            return cls.COMPACT
        if normalized in ("legacy_json",):
            return cls.FULL
        return cls.FULL


# ── Internal routing map ────────────────────────────────────────────────────

PROFILE_ROUTING: dict[OutputProfile, dict[str, Any]] = {
    OutputProfile.COMPACT: {
        "skip_edition": True,
        "dfg": None,
        "evidence_depth": "minimal",
        "gate_enforce": False,
        "quality_decision": False,
        "partial_result": False,
        "editions": ("mirror",),
        "description": "Mirror + Markdown only",
    },
    OutputProfile.FULL: {
        "skip_edition": False,
        "dfg": "structure_v2",
        "evidence_depth": "standard",
        "gate_enforce": False,
        "quality_decision": False,
        "partial_result": False,
        "editions": ("mirror", "community", "enterprise", "finance"),
        "description": "Mirror + Markdown + Edition + DFG v2 (default)",
    },
    OutputProfile.GA_FULL: {
        "skip_edition": False,
        "dfg": "ga_full",
        "evidence_depth": "full",
        "gate_enforce": True,
        "quality_decision": True,
        "partial_result": True,
        "editions": ("mirror", "community", "enterprise", "finance"),
        "description": "full + quality_decision + partial_result + DGC gate",
    },
    OutputProfile.FORENSIC: {
        "skip_edition": False,
        "dfg": "forensic",
        "evidence_depth": "forensic",
        "gate_enforce": True,
        "quality_decision": True,
        "partial_result": True,
        "editions": ("mirror", "community", "enterprise", "finance"),
        "description": "ga_full + noise preservation + full bbox + full DFG",
    },
}


__all__ = ["OutputProfile", "PROFILE_ROUTING"]
