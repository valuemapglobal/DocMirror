# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Input Resource Gate — unified pre-decode budget and security check.

Every input (file, PDF, image, archive, REST upload) MUST pass through a
resource gate BEFORE deep decoding. The gate checks size budgets, structure
limits, and known attack vectors (zip bomb, pixel bomb, path traversal, etc.).

Design reference: docs/design/GA1.0/12_privacy_security_compliance_ga_gap_closure_plan.md Wave 3.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from docmirror.security.security_ledger import ResourceGateDecision

# Default resource limits (can be overridden via env or settings)
DEFAULT_LIMITS = {
    "archive": {
        "max_entries": 200,
        "max_depth": 10,
        "max_uncompressed_size": 500_000_000,  # 500 MB
        "max_compression_ratio": 100,
        "max_single_entry_size": 200_000_000,
    },
    "pdf": {
        "max_file_size": 500_000_000,
        "max_pages": 2000,
        "max_object_count": 500_000,
        "allow_embedded_files": False,
        "allow_javascript": False,
    },
    "image": {
        "max_dimensions": 16384,  # pixels per side
        "max_pixels": 268_435_456,  # ~268 MP (16384x16384)
        "max_channels": 4,
        "max_frame_count": 1,
        "max_file_size": 200_000_000,
    },
    "rest_upload": {
        "max_body_size": 500_000_000,
        "max_temp_quota": 2_000_000_000,
        "allowed_content_types": [
            "application/pdf",
            "image/png",
            "image/jpeg",
            "image/tiff",
            "application/zip",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ],
    },
}


class ResourceGateBlockedError(Exception):
    """Raised when a resource gate check blocks the input."""

    def __init__(self, component: str, code: str, reason: str = ""):
        self.component = component
        self.code = code
        self.reason = reason
        super().__init__(f"[{component}] {code}: {reason}")


@dataclass
class ArchivePreflightResult:
    """Result of an archive resource preflight check."""

    allowed: bool
    code: str = "archive_resource_limit"
    file_size: int = 0
    entry_count: int = 0
    max_depth: int = 0
    uncompressed_size: int = 0
    compression_ratio: float = 0.0
    has_symlinks: bool = False
    has_unsafe_paths: bool = False
    blocked_reason: str = ""


@dataclass
class PDFPreflightResult:
    """Result of a PDF resource preflight check."""

    allowed: bool
    code: str = "pdf_resource_limit"
    file_size: int = 0
    page_count: int = 0
    has_embedded_files: bool = False
    has_javascript: bool = False
    is_encrypted: bool = False
    blocked_reason: str = ""


@dataclass
class ImagePreflightResult:
    """Result of an image resource preflight check."""

    allowed: bool
    code: str = "image_resource_limit"
    width: int = 0
    height: int = 0
    pixel_count: int = 0
    channels: int = 0
    frame_count: int = 1
    file_size: int = 0
    blocked_reason: str = ""


def _get_limit(component: str, key: str, default: Any) -> Any:
    """Get a limit value, checking env vars first."""
    env_key = f"DOCMIRROR_{component.upper()}_{key.upper()}"
    env_val = os.environ.get(env_key)
    if env_val is not None:
        try:
            if isinstance(default, bool):
                return env_val.strip().lower() in ("1", "true", "yes")
            if isinstance(default, int):
                return int(env_val)
            if isinstance(default, float):
                return float(env_val)
            return env_val
        except (ValueError, TypeError):
            pass
    return DEFAULT_LIMITS.get(component, {}).get(key, default)


def check_archive_preflight(
    filepath: str,
    entry_count: int = 0,
    max_depth: int = 0,
    uncompressed_size: int = 0,
    file_size: int = 0,
    has_symlinks: bool = False,
    has_unsafe_paths: bool = False,
) -> ArchivePreflightResult:
    """Check archive input against resource limits."""
    max_entries = _get_limit("archive", "max_entries", 200)
    max_depth_limit = _get_limit("archive", "max_depth", 10)
    max_uncompressed = _get_limit("archive", "max_uncompressed_size", 500_000_000)
    max_ratio = _get_limit("archive", "max_compression_ratio", 100)

    actual_size = file_size or (os.path.getsize(filepath) if os.path.exists(filepath) else 0)
    ratio = uncompressed_size / max(actual_size, 1)

    checks: list[tuple[bool, str]] = [
        (entry_count <= max_entries, f"entry_count={entry_count} exceeds max={max_entries}"),
        (max_depth <= max_depth_limit, f"depth={max_depth} exceeds max={max_depth_limit}"),
        (
            uncompressed_size <= max_uncompressed,
            f"uncompressed_size={uncompressed_size} exceeds max={max_uncompressed}",
        ),
        (ratio <= max_ratio, f"compression_ratio={ratio:.1f} exceeds max={max_ratio}"),
        (not has_unsafe_paths, "unsafe path detected"),
        (not has_symlinks, "symlinks not allowed"),
    ]

    blocked = [reason for ok, reason in checks if not ok]
    allowed = len(blocked) == 0

    return ArchivePreflightResult(
        allowed=allowed,
        code="archive_resource_limit" if not allowed else "archive_ok",
        file_size=actual_size,
        entry_count=entry_count,
        max_depth=max_depth,
        uncompressed_size=uncompressed_size,
        compression_ratio=ratio,
        has_symlinks=has_symlinks,
        has_unsafe_paths=has_unsafe_paths,
        blocked_reason="; ".join(blocked) if blocked else "",
    )


def check_pdf_preflight(
    filepath: str = "",
    file_size: int = 0,
    page_count: int = 0,
    has_embedded_files: bool = False,
    has_javascript: bool = False,
    is_encrypted: bool = False,
) -> PDFPreflightResult:
    """Check PDF input against resource limits."""
    max_size = _get_limit("pdf", "max_file_size", 500_000_000)
    max_pages = _get_limit("pdf", "max_pages", 2000)
    allow_embedded = _get_limit("pdf", "allow_embedded_files", False)
    allow_js = _get_limit("pdf", "allow_javascript", False)

    actual_size = file_size or (os.path.getsize(filepath) if filepath and os.path.exists(filepath) else 0)

    checks: list[tuple[bool, str]] = [
        (actual_size <= max_size, f"file_size={actual_size} exceeds max={max_size}"),
        (page_count <= max_pages, f"page_count={page_count} exceeds max={max_pages}"),
        (not has_embedded_files or allow_embedded, "embedded files not allowed"),
        (not has_javascript or allow_js, "JavaScript not allowed"),
    ]

    blocked = [reason for ok, reason in checks if not ok]
    allowed = len(blocked) == 0

    return PDFPreflightResult(
        allowed=allowed,
        code="pdf_resource_limit" if not allowed else "pdf_ok",
        file_size=actual_size,
        page_count=page_count,
        has_embedded_files=has_embedded_files,
        has_javascript=has_javascript,
        is_encrypted=is_encrypted,
        blocked_reason="; ".join(blocked) if blocked else "",
    )


def check_image_preflight(
    width: int = 0,
    height: int = 0,
    channels: int = 3,
    frame_count: int = 1,
    file_size: int = 0,
) -> ImagePreflightResult:
    """Check image input against resource limits."""
    max_dim = _get_limit("image", "max_dimensions", 16384)
    max_pixels = _get_limit("image", "max_pixels", 268_435_456)
    max_channels = _get_limit("image", "max_channels", 4)
    max_frames = _get_limit("image", "max_frame_count", 1)
    max_size = _get_limit("image", "max_file_size", 200_000_000)

    pixels = width * height

    checks: list[tuple[bool, str]] = [
        (width <= max_dim and height <= max_dim, f"dimensions={width}x{height} exceed max={max_dim}"),
        (pixels <= max_pixels, f"pixels={pixels} exceed max={max_pixels}"),
        (channels <= max_channels, f"channels={channels} exceed max={max_channels}"),
        (frame_count <= max_frames, f"frames={frame_count} exceed max={max_frames}"),
        (file_size <= max_size, f"file_size={file_size} exceed max={max_size}"),
    ]

    blocked = [reason for ok, reason in checks if not ok]
    allowed = len(blocked) == 0

    return ImagePreflightResult(
        allowed=allowed,
        code="image_resource_limit" if not allowed else "image_ok",
        width=width,
        height=height,
        pixel_count=pixels,
        channels=channels,
        frame_count=frame_count,
        file_size=file_size,
        blocked_reason="; ".join(blocked) if blocked else "",
    )


def check_rest_upload(
    content_type: str = "",
    body_size: int = 0,
) -> ResourceGateDecision:
    """Check REST upload against security limits."""
    max_body = _get_limit("rest_upload", "max_body_size", 500_000_000)
    allowed_types = _get_limit("rest_upload", "allowed_content_types", ["application/pdf"])

    checks: list[tuple[bool, str]] = [
        (body_size <= max_body, f"body_size={body_size} exceeds max={max_body}"),
    ]

    if allowed_types and content_type:
        checks.append(
            (
                content_type in allowed_types,
                f"content_type={content_type} not in allowlist",
            )
        )

    blocked = [reason for ok, reason in checks if not ok]
    status = "pass" if not blocked else "blocked"

    return ResourceGateDecision(
        component="rest_upload_gate",
        status=status,
        code="rest_upload_blocked" if blocked else "rest_upload_ok",
        input_metrics={"body_size": body_size, "content_type": content_type},
        limits={"max_body_size": max_body, "allowed_content_types": allowed_types},
    )


def to_ledger_decision(
    component: str,
    status: str,
    code: str,
    input_metrics: dict[str, Any],
    limits: dict[str, Any],
) -> ResourceGateDecision:
    """Create a standardized ResourceGateDecision for the security ledger."""
    return ResourceGateDecision(
        component=component,
        status=status,
        code=code,
        input_metrics=input_metrics,
        limits=limits,
    )
