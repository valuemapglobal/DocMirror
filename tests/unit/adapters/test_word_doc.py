# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for WordAdapter .doc handling via dispatcher (TranscodingGate)."""

from pathlib import Path
from unittest.mock import patch

import pytest

from docmirror.input.pipeline import perceive_document


@pytest.mark.asyncio
async def test_perceive_doc_without_soffice_returns_recoverable_failure(tmp_path):
    """When file is .doc and soffice is not found, dispatcher returns FORMAT_REQUIRES_CONVERTER."""
    doc = tmp_path / "sample.doc"
    doc.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 128)
    with patch("shutil.which", return_value=None):
        result = await perceive_document(doc)
    view = result.to_read_view()
    assert view.status.value == "failure"
    assert view.error is not None
    assert view.error.code == "FORMAT_REQUIRES_CONVERTER"
    assert "LibreOffice" in view.error.message or "soffice" in view.error.message
