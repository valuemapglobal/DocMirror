"""Unified ParseRequest and InputRef for all DocMirror integration surfaces.

CLI, SDK, REST, Docker, RAG, and Agent consumers all construct the same
``ParseRequest`` shape.  Surface-specific adapters (Click, FastAPI, gRPC,
in-process) are responsible for translating their native representation
into this canonical form before calling the shared orchestration layer.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
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

    # A task may contain one or more heterogeneous documents.
    inputs: list[InputRef] = field(default_factory=list)

    # -- execution control --
    mode: str = "auto"  # auto | fast | balanced | accurate | forensic

    # -- page selection --
    pages: str | None = None  # "1-3,8,10-"
    max_pages: int | None = None
    ocr: str = "auto"  # auto | force | off | fallback
    ocr_correction: str = "safe"  # off | safe | suggest
    ocr_language: str | None = None
    ocr_country: str | None = None
    ocr_locale: str | None = None
    ocr_correction_packs: list[str] = field(default_factory=list)
    page_split: str = "auto"  # auto | off | force

    # -- domain hints --
    doc_type: str | None = None
    doc_type_policy: str = "prefer"  # prefer | force

    # -- resource / runtime control --
    workers: int | str | None = None

    # -- extras (forward-compatible bag) --
    extras: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_policy(
        cls,
        inputs: list[InputRef],
        policy: Any,
        *,
        pages: str | None = None,
        max_pages: int | None = None,
        workers: int | str | None = None,
    ) -> ParseRequest:
        """Build the canonical request from an already normalized ParsePolicy."""
        hint = policy.doc_type_hint
        if pages is None and not policy.pages.is_all_pages:
            pages = policy.pages.to_display().split(" (max ", 1)[0]
        return cls(
            inputs=inputs,
            mode=policy.mode,
            pages=pages,
            max_pages=max_pages if max_pages is not None else policy.pages.max_pages,
            ocr=policy.ocr,
            ocr_correction=policy.ocr_correction,
            ocr_language=policy.ocr_language,
            ocr_country=policy.ocr_country,
            ocr_locale=policy.ocr_locale,
            ocr_correction_packs=list(policy.ocr_correction_packs),
            page_split=policy.page_split,
            doc_type=hint.value if hint else None,
            doc_type_policy=hint.strength if hint else "prefer",
            workers=workers,
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["inputs"] = [item.to_dict() for item in self.inputs]
        return {k: v for k, v in d.items() if v is not None and v != {}}
