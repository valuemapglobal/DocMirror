# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Dataclasses for Format Capability Registry."""

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
