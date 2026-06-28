"""Ownership helpers for RegionGraph diagnostics."""

from __future__ import annotations

from docmirror.structure.region_graph.models import OwnershipLedger


def ownership_stats(ledger: OwnershipLedger) -> dict[str, int]:
    return {
        "owned": len(ledger.owned),
        "nested": len(ledger.nested),
        "overlay": len(ledger.overlay),
        "suppressed_noise": len(ledger.suppressed_noise),
        "residual": len(ledger.residual),
        "rejected_candidates": len(ledger.rejected_candidates),
    }
