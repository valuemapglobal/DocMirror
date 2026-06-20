# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Transcoding gate — disk-to-disk format normalization before primary extraction.

Converts legacy or unsupported on-disk formats (``.doc``, ``.xls``, ``.ppt``,
etc.) into canonical types (``.docx``, ``.xlsx``, ``.pptx``) using external
converters when required by the Format Capability Registry. Exposes
``transcode_session`` context manager and ``FormatRequiresConverterError``.
"""

from __future__ import annotations

import asyncio
import email
import logging
import shutil
import subprocess
import tempfile
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from docmirror.configs.format.models import TranscodeSpec

logger = logging.getLogger(__name__)

_LIBREOFFICE_TARGETS = frozenset({"pdf", "docx", "xlsx", "pptx", "html"})


class FormatRequiresConverterError(Exception):
    """Raised when a required converter tool is missing or conversion fails."""

    def __init__(self, message: str, code: str = "FORMAT_REQUIRES_CONVERTER") -> None:
        super().__init__(message)
        self.code = code


@dataclass
class TranscodeResult:
    path: Path
    cleanup: Callable[[], None]


def _libreoffice_convert(source: Path, target_ext: str) -> Path:
    soffice = shutil.which("soffice")
    if not soffice:
        raise FormatRequiresConverterError(
            "LibreOffice (soffice) is required for this file format. "
            "Install LibreOffice or convert to a supported format.",
        )
    if target_ext not in _LIBREOFFICE_TARGETS:
        raise FormatRequiresConverterError(f"Unsupported LibreOffice target: {target_ext}")

    out_dir = tempfile.mkdtemp(prefix="docmirror_transcode_")
    cmd = [
        soffice,
        "--headless",
        "--convert-to",
        target_ext,
        "--outdir",
        out_dir,
        str(source),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
        if proc.returncode != 0:
            raise FormatRequiresConverterError(
                f"LibreOffice conversion failed: {proc.stderr or proc.stdout or proc.returncode}"
            )
        candidates = list(Path(out_dir).glob(f"*.{target_ext}"))
        if not candidates:
            raise FormatRequiresConverterError(f"LibreOffice produced no .{target_ext} output for {source.name}")
        dest = Path(tempfile.mkstemp(suffix=f".{target_ext}", prefix="docmirror_")[1])
        shutil.copy2(candidates[0], dest)

        def _cleanup() -> None:
            shutil.rmtree(out_dir, ignore_errors=True)
            try:
                dest.unlink(missing_ok=True)
            except OSError:
                pass

        return dest
    except subprocess.TimeoutExpired as exc:
        shutil.rmtree(out_dir, ignore_errors=True)
        raise FormatRequiresConverterError("LibreOffice conversion timed out") from exc


def _mhtml_to_html(source: Path) -> Path:
    raw = source.read_bytes()
    msg = email.message_from_bytes(raw)
    html_part = None
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                html_part = part
                break
    elif msg.get_content_type() == "text/html":
        html_part = msg

    if html_part is None:
        raise FormatRequiresConverterError("MHTML file contains no HTML part")

    payload = html_part.get_payload(decode=True)
    if payload is None:
        raise FormatRequiresConverterError("MHTML HTML part is empty")

    dest = Path(tempfile.mkstemp(suffix=".html", prefix="docmirror_mhtml_")[1])
    dest.write_bytes(payload)
    return dest


def _msg_to_eml(source: Path) -> Path:
    try:
        import extract_msg  # type: ignore[import-untyped]
    except ImportError as exc:
        raise FormatRequiresConverterError(
            "Outlook .msg files require optional dependency 'extract-msg'. Install with: pip install extract-msg",
        ) from exc

    msg = extract_msg.Message(str(source))
    try:
        msg_message = msg.as_email_message()
    finally:
        msg.close()

    dest = Path(tempfile.mkstemp(suffix=".eml", prefix="docmirror_msg_")[1])
    dest.write_bytes(msg_message.as_bytes())
    return dest


def transcode_sync(path: Path, spec: TranscodeSpec) -> TranscodeResult:
    """Synchronous transcode; returns temp path and cleanup callback."""
    tool = spec.tool
    target = spec.target

    if tool == "libreoffice":
        out = _libreoffice_convert(path, target)
    elif tool == "internal" and target == "html":
        out = _mhtml_to_html(path)
    elif tool == "extract_msg" and target == "eml":
        out = _msg_to_eml(path)
    else:
        raise FormatRequiresConverterError(f"Unsupported transcode: tool={tool} target={target}")

    logger.info("[TranscodingGate] %s → %s via %s", path.name, out.name, tool)

    def _cleanup() -> None:
        try:
            out.unlink(missing_ok=True)
        except OSError:
            pass

    return TranscodeResult(path=out, cleanup=_cleanup)


@asynccontextmanager
async def transcode_session(
    path: Path,
    spec: TranscodeSpec | None,
) -> AsyncIterator[Path]:
    """Async context manager yielding work path (original or transcoded temp)."""
    if spec is None:
        yield path
        return

    result = await asyncio.to_thread(transcode_sync, path, spec)
    try:
        yield result.path
    finally:
        result.cleanup()
