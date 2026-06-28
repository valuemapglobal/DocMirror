"""Unified ParseRequest and InputRef for all DocMirror integration surfaces.

CLI, SDK, REST, Docker, RAG, and Agent consumers all construct the same
``ParseRequest`` shape.  Surface-specific adapters (Click, FastAPI, gRPC,
in-process) are responsible for translating their native representation
into this canonical form before calling the shared orchestration layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class InputRef:
    """Stable reference to a document input.

    At least one of ``file_path`` or ``data`` must be provided.
    ``file_id`` is required when the caller participates in task
    lifecycle (polling, downloads, support bundles).
    """

    file_path: str | None = None
    data: bytes | None = None
    file_id: str = "001"
    file_name: str = "document"
    mime_type: str | None = None
    language_hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None}


@dataclass
class ParseRequest:
    """Canonical parse request accepted by all DocMirror integration surfaces.

    Every surface (CLI, Python SDK, REST, Docker, RAG loader, Agent tool)
    must normalise its native representation into this shape. The shared
    service layer below the surfaces only ever sees ``ParseRequest``.
    """

    input: InputRef = field(default_factory=InputRef)

    # -- execution control --
    mode: str = "auto"               # auto | fast | balanced | accurate | forensic
    profile: str | None = None       # compact | full | forensic | ga_full
    sync: bool = True                # False -> task-mode

    # -- page / geometry control --
    pages: str | None = None         # "1-3,8,10-"
    max_pages: int | None = None
    geometry: str | None = None      # none | page | block | token | full
    include_text: bool = False
    mirror_level: str = "standard"   # standard | forensic

    # -- output control --
    formats: list[str] = field(default_factory=lambda: ["json"])
    editions: list[str] = field(default_factory=lambda: ["mirror", "community"])
    ocr: str = "auto"                # auto | force | off | fallback
    cache_policy: str = "read-write" # read-write | read-only | refresh | off

    # -- domain hints --
    doc_type: str | None = None
    doc_type_policy: str = "prefer"  # prefer | force

    # -- resource / runtime control --
    workers: int | str | None = None

    # -- extras (forward-compatible bag) --
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.input is not None:
            d["input"] = self.input.to_dict()
        return {k: v for k, v in d.items() if v is not None and v != {}}
