# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""Unit tests for WordAdapter .doc handling (G1: FORMAT_REQUIRES_CONVERTER when no soffice)."""

import pytest
from pathlib import Path
from unittest.mock import patch

from docmirror.adapters.office.word import WordAdapter


@pytest.mark.asyncio
async def test_perceive_doc_without_soffice_returns_recoverable_failure():
    """When file is .doc and soffice is not found, return failure with FORMAT_REQUIRES_CONVERTER."""
    with patch("shutil.which", return_value=None):
        adapter = WordAdapter()
        path = Path("/tmp/sample.doc")
        result = await adapter.perceive(path)
        assert result.status.value == "failure"
        assert result.error is not None
        assert result.error.code == "FORMAT_REQUIRES_CONVERTER"
        assert result.error.recoverable is True
        assert "LibreOffice" in result.error.message or "soffice" in result.error.message