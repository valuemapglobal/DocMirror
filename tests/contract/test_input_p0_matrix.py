# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""P0 Input Coverage Contract Tests — WebP, PDF, Image, Resource Gates, Error Envelope.

Covers: INP-01 (WebP), INP-02 (PDF encrypted/damaged), INP-03 (file size),
INP-05 (invalid image), INP-09 (error envelope).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from docmirror.configs.format.loader import load_format_registry
from docmirror.configs.format.resolver import resolve_capability
from docmirror.models.errors import DocMirrorErrorCode, get_error_meta
from docmirror.input.acceptance import check_input_acceptance
from docmirror.input.pdf_probe import probe_pdf
from docmirror.input.image_probe import probe_image


# ── INP-01: WebP FCR / Support Matrix ──

def test_webp_in_fcr():
    caps, _ext_map, mime_map = load_format_registry()
    assert "image_raster" in caps, "image_raster capability missing in FCR"
    assert "image/webp" in mime_map.values(), "no mime_map entry for image/webp"


def test_webp_resolver():
    cap = resolve_capability(Path("scan.webp"), "image/webp")
    assert cap.id == "image_raster", f"WebP should resolve to image_raster, got {cap.id}"
    assert cap.status == "supported", f"WebP should be supported, got {cap.status}"


# ── INP-02: PDF encrypted/damaged ──

def test_encrypted_pdf_error_code():
    meta = get_error_meta("ENCRYPTED_PDF")
    assert meta["recoverable"] is True


def test_damaged_pdf_error_code():
    meta = get_error_meta("DAMAGED_PDF")
    assert meta["recoverable"] is True


# ── INP-03: File size resource gate ──

def test_file_too_small_error_code():
    meta = get_error_meta("FILE_TOO_SMALL")
    assert meta["recoverable"] is False


def test_file_too_large_error_code():
    meta = get_error_meta("FILE_TOO_LARGE")
    assert meta["recoverable"] is False


# ── INP-05: Invalid image ──

def test_invalid_image_error_code():
    meta = get_error_meta("INVALID_IMAGE")
    assert meta["recoverable"] is True


def test_low_quality_image_error_code():
    meta = get_error_meta("LOW_QUALITY_IMAGE")
    assert meta["recoverable"] is True


# ── INP-09: Error envelope ──

def test_empty_result_error_code():
    meta = get_error_meta("EMPTY_RESULT")
    assert meta["recoverable"] is True


def test_archive_resource_limit_error_code():
    meta = get_error_meta("ARCHIVE_RESOURCE_LIMIT")
    assert meta["recoverable"] is False


def test_archive_unsafe_path_error_code():
    meta = get_error_meta("ARCHIVE_UNSAFE_PATH")
    assert meta["recoverable"] is False


# ── Input acceptance ──

def test_input_acceptance_file_not_found(tmp_path: Path):
    missing = tmp_path / "nonexistent.pdf"
    report = check_input_acceptance(missing)
    assert not report.decision.accepted
    assert report.decision.reason == "FILE_NOT_FOUND"


def test_input_acceptance_unsupported_extension(tmp_path: Path):
    f = tmp_path / "test.xyz"
    f.write_text("d" * 500)  # 500 bytes — large enough to pass resource gate, still unsupported
    report = check_input_acceptance(f)
    assert not report.decision.accepted
    assert report.decision.reason == "UNSUPPORTED_FORMAT"


def test_input_acceptance_empty_file(tmp_path: Path):
    f = tmp_path / "empty.pdf"
    f.touch()
    report = check_input_acceptance(f)
    assert not report.decision.accepted
    # 0-byte file triggers resource gate: too small
    assert "FILE_TOO_SMALL" in report.decision.reason
