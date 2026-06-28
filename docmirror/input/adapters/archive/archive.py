# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Archive Adapter — .zip / .rar → ParseResult
===========================================

Decompresses batch-upload archives (no password support) and runs the full
``perceive()`` pipeline on every supported child file.  Nested archives are
extracted recursively up to a depth limit.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from docmirror.framework.base import BaseParser

logger = logging.getLogger(__name__)

_SKIP_DIR_NAMES = {"__MACOSX", ".git", "node_modules"}
_SKIP_FILE_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}
_MAX_CHILD_FILES = 200
_MAX_ARCHIVE_DEPTH = 3

_PASSWORD_MSG = "Password-protected archives are not supported yet. Please provide an unencrypted archive."


class ArchivePasswordProtectedError(Exception):
    """Raised when an archive requires a password for extraction."""


@dataclass
class _ChildOutcome:
    pages: list = field(default_factory=list)
    summaries: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    min_confidence: float = 1.0
    parsed_count: int = 0


def _is_skipped(path: Path) -> bool:
    for part in path.parts:
        if part in _SKIP_DIR_NAMES or part.startswith("."):
            return True
    return path.name in _SKIP_FILE_NAMES


def zip_requires_password(zf: zipfile.ZipFile) -> bool:
    """Return True if the ZIP cannot be read without a password."""
    if any(info.flag_bits & 0x1 for info in zf.infolist()):
        return True
    for info in zf.infolist():
        if info.is_dir():
            continue
        try:
            with zf.open(info) as fp:
                fp.read(1)
        except RuntimeError as exc:
            msg = str(exc).lower()
            if "password" in msg or "encrypted" in msg:
                return True
            raise
    return False


def _safe_member_path(dest: Path, member_name: str) -> Path:
    target = (dest / member_name).resolve()
    if not str(target).startswith(str(dest.resolve())):
        raise ValueError(f"Unsafe path in archive: {member_name}")
    return target


def _safe_extract_zip(zf: zipfile.ZipFile, dest: Path) -> None:
    dest = dest.resolve()
    for member in zf.namelist():
        _safe_member_path(dest, member)
    zf.extractall(dest)


def _safe_extract_rar(rf, dest: Path) -> None:
    dest = dest.resolve()
    for member in rf.infolist():
        _safe_member_path(dest, member.filename)
    rf.extractall(dest)


def _extract_archive(archive_path: Path, dest: Path) -> None:
    suffix = archive_path.suffix.lower()
    if suffix == ".zip":
        with zipfile.ZipFile(archive_path, "r") as zf:
            if zip_requires_password(zf):
                raise ArchivePasswordProtectedError(_PASSWORD_MSG)
            try:
                _safe_extract_zip(zf, dest)
            except RuntimeError as exc:
                if "password" in str(exc).lower() or "encrypted" in str(exc).lower():
                    raise ArchivePasswordProtectedError(_PASSWORD_MSG) from exc
                raise
        return

    if suffix == ".rar":
        try:
            import rarfile  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "RAR extraction requires the optional 'rarfile' package "
                "(pip install 'docmirror[archive]') and the unrar binary on PATH."
            ) from exc
        with rarfile.RarFile(archive_path) as rf:
            if rf.needs_password():
                raise ArchivePasswordProtectedError(_PASSWORD_MSG)
            try:
                _safe_extract_rar(rf, dest)
            except Exception as exc:
                if type(exc).__name__ in ("PasswordRequired", "RarWrongPassword") or ("password" in str(exc).lower()):
                    raise ArchivePasswordProtectedError(_PASSWORD_MSG) from exc
                raise
        return

    raise ValueError(f"Unsupported archive format: {suffix}")


def _collect_document_paths(root: Path) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIR_NAMES and not d.startswith(".")]
        for name in filenames:
            if name in _SKIP_FILE_NAMES or name.startswith("."):
                continue
            candidate = Path(dirpath) / name
            if _is_skipped(candidate.relative_to(root)):
                continue
            files.append(candidate)
    files.sort()
    return files[:_MAX_CHILD_FILES]


class ArchiveAdapter(BaseParser):
    """Zip/RAR batch adapter — extract, then ``perceive()`` every child file."""

    async def perceive(self, file_path: Path, **context) -> ParseResult:
        """Extract archive and analyze each child through the full middleware pipeline."""
        return await self._build_merged_result(file_path, parent_context=context)

    async def to_parse_result(self, file_path: Path, **kwargs) -> ParseResult:
        """Same as ``perceive`` — child files always receive full analysis."""
        context = dict(kwargs)
        if "enhance_mode" in kwargs:
            context["enhance_mode"] = kwargs["enhance_mode"]
        return await self._build_merged_result(file_path, parent_context=context)

    async def _build_merged_result(
        self,
        file_path: Path,
        *,
        parent_context: dict | None = None,
        depth: int = 0,
    ) -> ParseResult:
        from docmirror.models.entities.parse_result import (
            ParseResult,
            ParserInfo,
            ProvenanceInfo,
            ResultStatus,
        )
        from docmirror.models.errors import build_failure_result

        parent_context = parent_context or {}
        enhance_mode = parent_context.get("enhance_mode") or os.environ.get("DOCMIRROR_ENHANCE_MODE", "standard")

        logger.info(f"[ArchiveAdapter] Extracting archive (depth={depth}): {file_path}")

        tmp_dir = Path(tempfile.mkdtemp(prefix="docmirror_archive_"))
        try:
            try:
                _extract_archive(file_path, tmp_dir)
            except ArchivePasswordProtectedError as exc:
                return build_failure_result(
                    "ARCHIVE_PASSWORD_PROTECTED",
                    str(exc),
                    file_path=str(file_path),
                    file_type="archive",
                )
            except ImportError as exc:
                return build_failure_result(
                    "FORMAT_REQUIRES_CONVERTER",
                    str(exc),
                    file_path=str(file_path),
                    file_type="archive",
                )
            except (zipfile.BadZipFile, ValueError, OSError) as exc:
                return build_failure_result(
                    "EXTRACTION_FAILED",
                    f"Archive extraction failed: {exc}",
                    file_path=str(file_path),
                    file_type="archive",
                )

            child_paths = _collect_document_paths(tmp_dir)
            if not child_paths:
                return build_failure_result(
                    "EXTRACTION_FAILED",
                    "Archive contains no files",
                    file_path=str(file_path),
                    file_type="archive",
                )

            outcome = await self._process_children(
                child_paths,
                enhance_mode=enhance_mode,
                depth=depth,
                parent_context=parent_context,
            )

            if not outcome.pages:
                detail = "; ".join(outcome.skipped[:5]) if outcome.skipped else ""
                msg = "No supported documents could be parsed inside archive"
                if detail:
                    msg = f"{msg}: {detail}"
                return build_failure_result(
                    "EXTRACTION_FAILED",
                    msg,
                    file_path=str(file_path),
                    file_type="archive",
                )

            attempted = len(child_paths)
            status = (
                ResultStatus.SUCCESS
                if outcome.parsed_count == attempted and not outcome.skipped
                else ResultStatus.PARTIAL
            )

            try:
                stat = file_path.stat()
                provenance = ProvenanceInfo(file_type="archive", file_size=stat.st_size)
            except OSError:
                provenance = ProvenanceInfo(file_type="archive")

            warnings = [f"parsed {outcome.parsed_count}/{attempted} files: " + ", ".join(outcome.summaries)]
            if outcome.skipped:
                warnings.append("skipped: " + "; ".join(outcome.skipped[:10]))

            return ParseResult(
                status=status,
                confidence=outcome.min_confidence if outcome.parsed_count else 0.0,
                pages=outcome.pages,
                parser_info=ParserInfo(
                    parser_name="ArchiveAdapter",
                    page_count=len(outcome.pages),
                    overall_confidence=outcome.min_confidence,
                    warnings=warnings,
                ),
                provenance=provenance,
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    async def _process_children(
        self,
        child_paths: list[Path],
        *,
        enhance_mode: str,
        depth: int,
        parent_context: dict,
    ) -> _ChildOutcome:
        from docmirror.configs.format.resolver import resolve_capability
        from docmirror.framework.extraction_runner import (
            build_perceive_context,
            run_extraction_chain,
        )
        from docmirror.models.entities.parse_result import TextBlock, TextLevel

        outcome = _ChildOutcome()
        page_offset = 0

        for child in child_paths:
            child_cap = resolve_capability(child)
            child_type = child_cap.transport

            if child_type == "archive":
                if depth + 1 >= _MAX_ARCHIVE_DEPTH:
                    outcome.skipped.append(f"{child.name}: nested archive exceeds depth {_MAX_ARCHIVE_DEPTH}")
                    continue
                nested = await self._build_merged_result(
                    child,
                    parent_context=parent_context,
                    depth=depth + 1,
                )
                if not nested.success or not nested.pages:
                    outcome.skipped.append(f"{child.name}: nested archive parse failed")
                    continue
                outcome.parsed_count += 1
                outcome.min_confidence = min(outcome.min_confidence, nested.confidence)
                outcome.summaries.append(f"{child.name} (archive)")
                header = TextBlock(
                    content=f"── {child.name} (archive) ──",
                    level=TextLevel.H2,
                )
                nested.pages[0].texts = [header, *nested.pages[0].texts]
                for page in nested.pages:
                    page.page_number += page_offset
                    outcome.pages.append(page)
                page_offset = len(outcome.pages)
                continue

            if child_cap.status != "supported":
                outcome.skipped.append(f"{child.name}: {child_cap.status} ({child_cap.id})")
                continue

            member_name = child.name
            try:
                child_stat = child.stat()
                child_size = child_stat.st_size
            except OSError:
                child_size = 0

            child_ctx = build_perceive_context(
                child,
                child_cap,
                file_size=child_size,
                t0=time.time(),
            )
            child_ctx["enhance_mode"] = enhance_mode
            child_ctx["source_member"] = member_name
            if parent_context.get("started_at") is not None:
                child_ctx["started_at"] = parent_context["started_at"]

            t0 = time.time()
            try:
                child_result = await run_extraction_chain(
                    child_cap,
                    child,
                    child_ctx,
                    enhance_mode=enhance_mode,
                    t0=t0,
                )
            except Exception as exc:
                logger.warning(f"[ArchiveAdapter] Child parse failed {child.name}: {exc}")
                outcome.skipped.append(f"{child.name}: {exc}")
                continue

            elapsed_ms = int((time.time() - t0) * 1000)
            logger.info(
                f"[ArchiveAdapter] Child done | file={child.name} | "
                f"type={child_type} | status={child_result.status.value} | "
                f"elapsed={elapsed_ms}ms"
            )

            if not child_result.success or not child_result.pages:
                reason = child_result.error.message if child_result.error else "empty result"
                outcome.skipped.append(f"{child.name}: {reason}")
                continue

            outcome.parsed_count += 1
            outcome.min_confidence = min(outcome.min_confidence, child_result.confidence)
            outcome.summaries.append(f"{child.name} ({child_type})")

            header = TextBlock(
                content=f"── {child.name} ({child_type}) ──",
                level=TextLevel.H2,
            )
            child_result.pages[0].texts = [header, *child_result.pages[0].texts]
            for page in child_result.pages:
                page.page_number += page_offset
                page.source_member = member_name
                outcome.pages.append(page)
            page_offset = len(outcome.pages)

        return outcome
