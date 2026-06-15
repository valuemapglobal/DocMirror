# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
PerceiveResult envelope — mirror output plus optional edition payloads.

Purpose: Wraps the frozen Mirror ``ParseResult`` separately from optional
PEC edition outputs so ``001_mirror.json`` stays clean while editions can
carry enriched views.

Main components: ``PerceiveResult`` (delegates attribute access to ``mirror``).

Upstream: ``entry.factory`` after ``ParserDispatcher`` completes.

Downstream: API serializers and clients consuming ``to_api_dict()``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from docmirror.models.entities.parse_result import ParseResult


@dataclass
class PerceiveResult:
    """
    Envelope returned by ``perceive_document()``.

    ``mirror`` is the frozen Mirror ``ParseResult`` (safe for ``001_mirror.json``).
    ``editions`` holds optional PEC outputs keyed by edition name.

    Attribute access delegates to ``mirror`` for backward compatibility
    (``result.full_text``, ``result.page_count``, etc.).
    """

    mirror: ParseResult
    editions: dict[str, dict[str, Any]] = field(default_factory=dict)

    def __getattr__(self, name: str) -> Any:
        if name in ("mirror", "editions"):
            raise AttributeError(name)
        return getattr(self.mirror, name)

    def to_api_dict(self, **kwargs: Any) -> dict[str, Any]:
        return self.mirror.to_api_dict(**kwargs)
