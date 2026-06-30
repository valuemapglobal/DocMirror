# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
PerceiveResult envelope — mirror output plus optional edition payloads.

Purpose: Wraps the frozen Mirror ``ParseResult`` separately from optional
PEC edition outputs so ``001_mirror.json`` stays clean while editions can
carry enriched views.

Main components: ``PerceiveResult`` (delegates attribute access to ``mirror``).

Upstream: ``entry.factory`` after ``ParserDispatcher`` completes.

Downstream: API serializers and clients consuming ``to_mirror_json_vnext()``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PerceiveResult:
    """
    Envelope returned by ``perceive_document()``.

    ``mirror`` is the frozen Mirror ``ParseResult`` (safe for ``001_mirror.json``).
    ``editions`` holds optional PEC outputs keyed by edition name.

    Attribute access delegates to ``mirror`` for public result API stability
    (``result.full_text``, ``result.page_count``, etc.).
    """

    mirror: Any
    editions: dict[str, dict[str, Any]] = field(default_factory=dict)
    parse_result: Any | None = None

    def __post_init__(self) -> None:
        if self.parse_result is None:
            try:
                from docmirror.models.entities.parse_result import ParseResult

                if isinstance(self.mirror, ParseResult):
                    self.parse_result = self.mirror
            except Exception:
                pass

    def __getattr__(self, name: str) -> Any:
        if name in ("mirror", "editions", "parse_result"):
            raise AttributeError(name)
        if self.parse_result is not None and hasattr(self.parse_result, name):
            return getattr(self.parse_result, name)
        return getattr(self.mirror, name)

    def to_mirror_json_vnext(self, **kwargs: Any) -> dict[str, Any]:
        if hasattr(self.mirror, "model_dump"):
            return self.mirror.model_dump(by_alias=True, exclude_none=True)
        if isinstance(self.mirror, dict):
            return self.mirror
        if self.parse_result is not None and hasattr(self.parse_result, "to_mirror_json_vnext"):
            return self.parse_result.to_mirror_json_vnext(**kwargs)
        if hasattr(self.mirror, "to_mirror_json_vnext"):
            return self.mirror.to_mirror_json_vnext(**kwargs)
        return {"error": f"unexpected mirror type: {type(self.mirror).__name__}"}

    def sections_for_rag(self) -> list[dict[str, Any]]:
        from docmirror.framework.extension_points import resolve_sections

        return resolve_sections(self.parse_result or self.mirror, self.editions)
