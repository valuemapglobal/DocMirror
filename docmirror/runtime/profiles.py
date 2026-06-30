# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""DRC Cost Profile Resolver — compact/full/forensic mapping.

GA 1.0 §6.6: Cost profiles are independent of parse modes. The profile
resolver translates a cost profile name into concrete output-control
settings: mirror level, geometry granularity, evidence depth, chunk
strategy, visual debug policy, and size guards.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

CostProfileName = Literal["compact", "full", "forensic"]
MirrorLevel = Literal["standard", "forensic"]
GeometryLevel = Literal["block", "token", "full"]
EvidenceDepth = Literal["basic", "key_fields", "full"]
ChunkStrategy = Literal["large", "normal", "small"]
VlmPolicy = Literal["off", "optional", "optional_strict"]
VisualDebugPolicy = Literal["failure_only", "failure_sample", "sampled", "all"]


@dataclass(frozen=True)
class ProfileResolution:
    """Concrete output settings resolved from a cost profile."""

    profile_name: CostProfileName = "full"
    mirror_level: MirrorLevel = "standard"
    geometry: GeometryLevel = "token"
    include_text: bool = True
    evidence_depth: EvidenceDepth = "full"
    visual_debug: VisualDebugPolicy = "failure_sample"
    chunk_strategy: ChunkStrategy = "normal"
    vlm_policy: VlmPolicy = "optional"
    output_size_guard_bytes: int = 100 * 1024 * 1024
    max_chunk_chars: int = 2000
    chunk_overlap: int = 200
    token_budget_hard_limit: int = 200_000

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_name": self.profile_name,
            "mirror_level": self.mirror_level,
            "geometry": self.geometry,
            "include_text": self.include_text,
            "evidence_depth": self.evidence_depth,
            "visual_debug": self.visual_debug,
            "chunk_strategy": self.chunk_strategy,
            "vlm_policy": self.vlm_policy,
            "output_size_guard_bytes": self.output_size_guard_bytes,
            "max_chunk_chars": self.max_chunk_chars,
            "chunk_overlap": self.chunk_overlap,
            "token_budget_hard_limit": self.token_budget_hard_limit,
        }


# ── Profile definitions ───────────────────────────────────────────────

COMPACT_PROFILE = ProfileResolution(
    profile_name="compact",
    mirror_level="standard",
    geometry="block",
    include_text=True,
    evidence_depth="basic",
    visual_debug="failure_only",
    chunk_strategy="large",
    vlm_policy="off",
    output_size_guard_bytes=20 * 1024 * 1024,
    max_chunk_chars=3000,
    chunk_overlap=100,
    token_budget_hard_limit=100_000,
)

FULL_PROFILE = ProfileResolution(
    profile_name="full",
    mirror_level="standard",
    geometry="token",
    include_text=True,
    evidence_depth="full",
    visual_debug="failure_sample",
    chunk_strategy="normal",
    vlm_policy="optional",
    output_size_guard_bytes=100 * 1024 * 1024,
    max_chunk_chars=2000,
    chunk_overlap=200,
    token_budget_hard_limit=200_000,
)

FORENSIC_PROFILE = ProfileResolution(
    profile_name="forensic",
    mirror_level="forensic",
    geometry="full",
    include_text=True,
    evidence_depth="full",
    visual_debug="all",
    chunk_strategy="small",
    vlm_policy="optional_strict",
    output_size_guard_bytes=500 * 1024 * 1024,
    max_chunk_chars=1000,
    chunk_overlap=400,
    token_budget_hard_limit=500_000,
)

_PROFILE_MAP: dict[str, ProfileResolution] = {
    "compact": COMPACT_PROFILE,
    "full": FULL_PROFILE,
    "forensic": FORENSIC_PROFILE,
}


def resolve_profile(profile_name: str | CostProfileName) -> ProfileResolution:
    """Resolve a cost profile name to concrete settings.

    Unknown names fall back to ``full`` with a warning logged.
    """
    normalized = str(profile_name).lower().strip()
    if normalized in _PROFILE_MAP:
        return _PROFILE_MAP[normalized]

    import logging

    logging.getLogger(__name__).warning("Unknown cost profile '%s', falling back to 'full'", profile_name)
    return FULL_PROFILE


def profile_from_cli(profile_arg: str | None) -> ProfileResolution:
    """Resolve a profile from a CLI argument (may be None → default 'full')."""
    if profile_arg is None:
        return FULL_PROFILE
    return resolve_profile(profile_arg)


def profile_diff(
    a: ProfileResolution,
    b: ProfileResolution,
) -> dict[str, dict[str, Any]]:
    """Return a diff of differences between two profile resolutions."""
    a_dict = a.to_dict()
    b_dict = b.to_dict()
    diff: dict[str, dict[str, Any]] = {}
    for key in set(a_dict) | set(b_dict):
        va = a_dict.get(key)
        vb = b_dict.get(key)
        if va != vb:
            diff[key] = {"from": va, "to": vb}
    return diff


__all__ = [
    "COMPACT_PROFILE",
    "CostProfileName",
    "FORENSIC_PROFILE",
    "FULL_PROFILE",
    "ProfileResolution",
    "profile_diff",
    "profile_from_cli",
    "resolve_profile",
]
