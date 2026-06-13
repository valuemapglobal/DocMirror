# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.

"""Unit tests for archive adapter helpers."""

from __future__ import annotations

import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from docmirror.adapters.archive.archive import (
    ArchivePasswordProtectedError,
    _collect_document_paths,
    _extract_archive,
    zip_requires_password,
)
from docmirror.models.errors import get_error_meta


def test_zip_requires_password_plain():
    archive = Path(__file__).parent / "_fixtures_plain.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("readme.txt", "hello")
    try:
        with zipfile.ZipFile(archive, "r") as zf:
            assert zip_requires_password(zf) is False
    finally:
        archive.unlink(missing_ok=True)


def test_extract_password_protected_zip(tmp_path: Path):
    archive = tmp_path / "locked.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("doc.pdf", "content")

    dest = tmp_path / "out"
    dest.mkdir()

    with patch(
        "docmirror.adapters.archive.archive.zip_requires_password",
        return_value=True,
    ):
        with pytest.raises(ArchivePasswordProtectedError):
            _extract_archive(archive, dest)


def test_extract_runtime_password_error(tmp_path: Path):
    archive = tmp_path / "locked.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("doc.pdf", "content")

    dest = tmp_path / "out"
    dest.mkdir()

    def _raise_encrypted(zf, dest_dir):
        raise RuntimeError("File is encrypted, password required for extraction")

    with patch(
        "docmirror.adapters.archive.archive._safe_extract_zip",
        side_effect=_raise_encrypted,
    ):
        with pytest.raises(ArchivePasswordProtectedError):
            _extract_archive(archive, dest)


def test_extract_plain_zip_and_collect(tmp_path: Path):
    archive = tmp_path / "batch.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("invoice.pdf", b"%PDF-1.4")
        zf.writestr("data.csv", "a,b\n1,2")

    dest = tmp_path / "out"
    dest.mkdir()
    _extract_archive(archive, dest)

    files = _collect_document_paths(dest)
    names = {p.name for p in files}
    assert names == {"data.csv", "invoice.pdf"}


def test_archive_password_error_code_registered():
    meta = get_error_meta("ARCHIVE_PASSWORD_PROTECTED")
    assert meta["recoverable"] is False
    assert "Password-protected" in meta["user_message"]
