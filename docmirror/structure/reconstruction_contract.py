"""Contracts for UDTR region reconstructors."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ReconstructionContract:
    id: str
    accepted_region_kinds: list[str] = field(default_factory=list)
    required_evidence_kinds: list[str] = field(default_factory=list)
    optional_evidence_kinds: list[str] = field(default_factory=list)
    output_block_types: list[str] = field(default_factory=list)
    output_roles: list[str] = field(default_factory=list)
    failure_modes: list[str] = field(default_factory=list)
    fallback: str = "minimal_residual_reconstructor"
    quality_keys: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "accepted_region_kinds": list(self.accepted_region_kinds),
            "required_evidence_kinds": list(self.required_evidence_kinds),
            "optional_evidence_kinds": list(self.optional_evidence_kinds),
            "output_block_types": list(self.output_block_types),
            "output_roles": list(self.output_roles),
            "failure_modes": list(self.failure_modes),
            "fallback": self.fallback,
            "quality_keys": list(self.quality_keys),
        }


def default_contract(reconstructor: Any) -> ReconstructionContract:
    reconstructor_id = str(getattr(reconstructor, "id", type(reconstructor).__name__))
    kinds = sorted(str(kind) for kind in getattr(reconstructor, "supported_kinds", set()) or [])
    return ReconstructionContract(
        id=reconstructor_id,
        accepted_region_kinds=kinds,
        output_block_types=["unknown"],
        fallback="minimal_residual_reconstructor",
    )
