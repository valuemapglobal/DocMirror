# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Archive Probe — pre-extraction safety and resource checks.

Purpose: Scan archive central directory before extraction to detect:
    - Path traversal attacks
    - Zip bombs (excessive entries, size, compression ratio)
    - Password protection
    - Entry count / depth limits
"""

from __future__ import annotations

import logging
import os
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ArchiveProbeResult:
    """Archive probe outcome."""

    status: str = "unknown"  # ok | password | resource_limit | unsafe | unreadable
    entry_count: int = 0
    total_uncompressed: int = 0
    total_compressed: int = 0
    max_compression_ratio: float = 0.0
    max_member_size: int = 0
    max_depth: int = 0
    password_protected: bool = False
    has_unsafe_paths: bool = False
    unsafe_paths: list[str] = field(default_factory=list)
    error_code: str = ""
    error_message: str = ""
    format: str = ""


def probe_archive(
    path: Path,
    max_entries: int = 200,
    max_depth: int = 3,
    max_member_size: int = 104857600,
    max_total_uncompressed: int = 1073741824,
    max_compression_ratio: float = 100.0,
) -> ArchiveProbeResult:
    """Scan archive metadata without full extraction."""
    result = ArchiveProbeResult()

    if not path.is_file():
        result.status = "unreadable"
        result.error_code = "FILE_NOT_FOUND"
        result.error_message = f"File not found: {path}"
        return result

    suffix = path.suffix.lower()
    if suffix == ".zip":
        result.format = "zip"
        return _probe_zip(
            path, result, max_entries, max_depth, max_member_size, max_total_uncompressed, max_compression_ratio
        )
    elif suffix in (".rar",):
        result.format = "rar"
        result.status = "ok"
        return result
    else:
        result.status = "unreadable"
        result.error_code = "UNSUPPORTED_FORMAT"
        result.error_message = f"Unsupported archive format: {suffix}"
        return result


def _probe_zip(
    path: Path,
    result: ArchiveProbeResult,
    max_entries: int,
    max_depth: int,
    max_member_size: int,
    max_total_uncompressed: int,
    max_compression_ratio: float,
) -> ArchiveProbeResult:
    """Scan ZIP central directory for security and resource budget."""
    try:
        with zipfile.ZipFile(path, "r") as zf:
            infolist = zf.infolist()
            result.entry_count = len(infolist)

            # Password detection
            result.password_protected = any(info.flag_bits & 0x1 for info in infolist)
            if result.password_protected:
                result.status = "password"
                result.error_code = "ARCHIVE_PASSWORD_PROTECTED"
                result.error_message = "Password-protected archives are not supported"
                return result

            # Resource budget scan
            violations = []
            if result.entry_count > max_entries:
                violations.append(f"entry_count {result.entry_count} > max {max_entries}")

            for info in infolist:
                if info.is_dir():
                    continue
                member_uc = info.file_size
                member_c = info.compress_size
                result.total_uncompressed += member_uc
                result.total_compressed += member_c

                if member_uc > max_member_size:
                    violations.append(f"member {info.filename} size {member_uc} > max {max_member_size}")

                # Depth check
                depth = len(info.filename.strip("/").split("/"))
                if depth > result.max_depth:
                    result.max_depth = depth
                if depth > max_depth:
                    violations.append(f"member {info.filename} depth {depth} > max {max_depth}")

                # Compression ratio (zip bomb detection)
                if member_c > 0:
                    ratio = member_uc / member_c
                    if ratio > result.max_compression_ratio:
                        result.max_compression_ratio = ratio
                    if ratio > max_compression_ratio:
                        violations.append(
                            f"member {info.filename} compression ratio {ratio:.1f}x > max {max_compression_ratio}x"
                        )

                if member_uc > result.max_member_size:
                    result.max_member_size = member_uc

            if result.total_uncompressed > max_total_uncompressed:
                violations.append(f"total_uncompressed {result.total_uncompressed} > max {max_total_uncompressed}")

            # Path traversal detection
            unsafe = []
            for info in infolist:
                member_path = info.filename
                normalized = os.path.normpath(member_path)
                if normalized.startswith("..") or normalized.startswith("/") or ".." in normalized.split("/"):
                    unsafe.append(member_path)
            if unsafe:
                result.has_unsafe_paths = True
                result.unsafe_paths = unsafe
                result.status = "unsafe"
                result.error_code = "ARCHIVE_UNSAFE_PATH"
                result.error_message = f"Archive contains {len(unsafe)} unsafe path(s)"
                return result

            if violations:
                result.status = "resource_limit"
                result.error_code = "ARCHIVE_RESOURCE_LIMIT"
                result.error_message = "; ".join(violations)
                return result

            result.status = "ok"

    except zipfile.BadZipFile as e:
        result.status = "unreadable"
        result.error_code = "UNSUPPORTED_FORMAT"
        result.error_message = f"Bad ZIP file: {e}"
        logger.warning("[ArchiveProbe] Bad ZIP: %s — %s", path.name, e)
    except Exception as e:
        result.status = "unreadable"
        result.error_code = "PARSER_ERROR"
        result.error_message = str(e)
        logger.warning("[ArchiveProbe] Scan error: %s — %s", path.name, e)

    return result
