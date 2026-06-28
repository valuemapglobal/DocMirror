"""Minimal vNext MirrorJson output builder.

This module intentionally avoids heavy imports at module load. The full mirror
pipeline can evolve behind the same public contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from docmirror.output.serialization import to_json_safe


@dataclass(slots=True)
class MirrorOptions:
    source_filename: str = ""
    profile: str = "standard"


@dataclass(slots=True)
class MirrorResult:
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return to_json_safe(self.payload)


class MirrorCoreVNext:
    """Build the canonical document-shaped MirrorJson payload."""

    def process(self, result: Any, *, options: MirrorOptions | None = None) -> MirrorResult:
        options = options or MirrorOptions()
        entities = getattr(result, "entities", None)
        document_type = getattr(entities, "document_type", None) if entities is not None else None
        sections = to_json_safe(getattr(result, "sections", []) or [])
        table_operations = to_json_safe(getattr(result, "table_operations", []) or [])
        pages = to_json_safe(getattr(result, "pages", []) or [])
        status = getattr(getattr(result, "status", None), "value", getattr(result, "status", "success"))

        payload = {
            "mirror": {
                "schema": "docmirror.mirror_json",
                "schema_version": "3.0.0",
                "profile": options.profile,
            },
            "source": {
                "filename": options.source_filename,
                "provenance": {
                    "sections": sections,
                    "table_operations": table_operations,
                },
            },
            "document": {
                "document_type": document_type or "generic",
                "document_type_candidates": [],
            },
            "pages": pages,
            "evidence": {
                "text_atoms": [],
                "visual_atoms": [],
            },
            "regions": [],
            "blocks": [],
            "graph": {},
            "semantics": {
                "facts": [],
                "entities": [],
                "views": {},
            },
            "quality": {
                "overall": {
                    "status": "fail" if str(status) == "failure" else "pass",
                    "score": float(getattr(result, "confidence", 1.0) or 0.0),
                }
            },
            "diagnostics": {
                "pipeline": [],
            },
            "assets": {},
        }
        error = getattr(result, "error", None)
        if error is not None:
            payload["diagnostics"]["error"] = to_json_safe(error)
        return MirrorResult(payload)
