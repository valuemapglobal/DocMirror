# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Dataclasses for the Format Capability Registry (FCR).

Immutable frozen dataclasses describing how DocMirror routes a file format to
an extraction adapter, optional transcode step, and fallback chain.

Types::

    FormatCapability    Full capability record (id, transport, content_model, status, …)
    ExtractionBinding   Adapter name, transcode spec, fallback, deserializer, kwargs
    TranscodeSpec       External converter tool, target format, missing-tool error code
    FallbackSpec        Secondary adapter invoked on primary_empty or primary_failed
    UNKNOWN_CAPABILITY  Sentinel for unrecognized extensions/MIME types

``CapabilityStatus`` is one of ``supported``, ``planned``, or ``unsupported``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

CapabilityStatus = Literal["supported", "planned", "unsupported"]


@dataclass(frozen=True)
class TranscodeSpec:
    tool: str  # libreoffice | internal | extract_msg
    target: str  # pdf | docx | xlsx | pptx | eml | html
    on_missing: str = "FORMAT_REQUIRES_CONVERTER"


@dataclass(frozen=True)
class FallbackSpec:
    adapter: str
    when: str = "primary_empty"  # primary_empty | primary_failed


@dataclass(frozen=True)
class ExtractionBinding:
    adapter: str | None = None
    transcode: TranscodeSpec | None = None
    fallback: FallbackSpec | None = None
    deserializer: str | None = None
    kwargs: dict = field(default_factory=dict)


@dataclass(frozen=True)
class FormatCapability:
    id: str
    transport: str
    content_model: str
    status: CapabilityStatus
    extensions: frozenset[str] = frozenset()
    mime: frozenset[str] = frozenset()
    mime_prefix: str = ""
    binding: ExtractionBinding | None = None


UNKNOWN_CAPABILITY = FormatCapability(
    id="unknown",
    transport="unknown",
    content_model="opaque_binary",
    status="unsupported",
)
