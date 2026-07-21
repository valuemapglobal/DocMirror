# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""P0 Container / Web / Email Smoke Tests.

Covers: INP-08 (Email/Web/Archive adapter smoke).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from docmirror.configs.format.loader import load_format_registry
from docmirror.configs.format.resolver import resolve_capability

# ── Email (EML) ──

def test_eml_in_fcr():
    caps, _, _ = load_format_registry()
    assert "email_eml" in caps, "email_eml missing in FCR"


def test_html_in_fcr():
    caps, _, _ = load_format_registry()
    assert "web_html" in caps, "web_html missing in FCR"


def test_zip_in_fcr():
    caps, _, _ = load_format_registry()
    assert "archive_zip" in caps, "archive_zip missing in FCR"


def test_eml_resolver():
    cap = resolve_capability(Path("mail.eml"), "message/rfc822")
    assert cap.status == "supported", f"EML should be supported, got {cap.status}"


def test_html_resolver():
    cap = resolve_capability(Path("page.html"), "text/html")
    assert cap.status == "supported", f"HTML should be supported, got {cap.status}"


def test_zip_resolver():
    cap = resolve_capability(Path("files.zip"), "application/zip")
    assert cap.status == "supported", f"ZIP should be supported, got {cap.status}"


# ── Security matrix ──

def test_security_error_codes():
    from docmirror.models.errors import DocMirrorErrorCode
    codes = {e.value for e in DocMirrorErrorCode}
    for required in ("ARCHIVE_PASSWORD_PROTECTED", "ARCHIVE_RESOURCE_LIMIT", "ARCHIVE_UNSAFE_PATH"):
        assert required in codes, f"Missing error code: {required}"


def test_input_acceptance_report_serializable():
    from docmirror.input.models import InputAcceptanceReport
    report = InputAcceptanceReport()
    d = report.to_dict()
    assert isinstance(d, dict)
    assert d["version"] == 1
    assert not d["decision"]["accepted"]
