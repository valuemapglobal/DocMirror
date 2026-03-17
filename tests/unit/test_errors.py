"""Unit tests for docmirror.models.errors (G3 error codes and failure builder)."""

import pytest
from docmirror.models.errors import (
    DocMirrorErrorCode,
    get_error_meta,
    make_error_detail,
    build_failure_result,
)


class TestDocMirrorErrorCode:
    def test_known_codes_exist(self):
        assert DocMirrorErrorCode.FILE_NOT_FOUND.value == "FILE_NOT_FOUND"
        assert DocMirrorErrorCode.FORMAT_REQUIRES_CONVERTER.value == "FORMAT_REQUIRES_CONVERTER"

    def test_get_error_meta_returns_recoverable_and_user_message(self):
        meta = get_error_meta("FILE_NOT_FOUND")
        assert meta["recoverable"] is False
        assert "message" in meta or "user_message" in meta

    def test_get_error_meta_unknown_falls_back(self):
        meta = get_error_meta("UNKNOWN_CODE_XYZ")
        assert "recoverable" in meta

    def test_make_error_detail_sets_code_and_recoverable(self):
        detail = make_error_detail("FORMAT_REQUIRES_CONVERTER", "Install LibreOffice.")
        assert detail.code == "FORMAT_REQUIRES_CONVERTER"
        assert detail.recoverable is True
        assert "LibreOffice" in detail.message or len(detail.message) > 0

    def test_build_failure_result_produces_failure_status(self):
        result = build_failure_result(
            "UNSUPPORTED_FORMAT", "Unsupported format: xyz", file_path="/tmp/foo.xyz", file_type="unknown"
        )
        assert result.status.value == "failure"
        assert result.error is not None
        assert result.error.code == "UNSUPPORTED_FORMAT"
        assert result.content.text == ""
        assert result.provenance.source.file_path == "/tmp/foo.xyz"
