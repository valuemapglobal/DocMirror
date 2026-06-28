"""ObservabilityContext — cross-cutting request identity and diagnostics.

Every DocMirror operation (CLI parse, SDK call, REST request, task poll,
Docker health check) carries an ``ObservabilityContext`` that threads
request identity, version, profile, and warnings through logs, manifests,
quality reports, and artifacts so operators can correlate behaviour end
to end without parsing divergent log formats.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from typing import Any


def _new_request_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class ObservabilityContext:
    """Request-scoped observability metadata.

    Built once at the integration boundary and forwarded to every downstream
    log, manifest, quality report, and error envelope so the same
    ``request_id`` appears consistently.
    """

    request_id: str = field(default_factory=_new_request_id)
    version: str = "1.0.0"
    profile: str | None = None          # compact | full | forensic | ga_full
    entry: str = "unknown"              # cli | sdk | rest | docker | agent
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None and v != []}


def build_observability_context(
    version: str = "1.0.0",
    profile: str | None = None,
    entry: str = "unknown",
) -> ObservabilityContext:
    """Factory for the canonical observability context."""
    return ObservabilityContext(
        request_id=_new_request_id(),
        version=version,
        profile=profile,
        entry=entry,
    )
