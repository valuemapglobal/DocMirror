# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio

import pytest

from docmirror.sdk.client import _run_async


def test_sync_sdk_rejects_active_event_loop_with_actionable_message():
    async def _call_sync_bridge():
        async def _value():
            return 1

        with pytest.raises(RuntimeError, match="AsyncDocMirrorClient"):
            _run_async(_value())

    asyncio.run(_call_sync_bridge())


def test_pdfua_extra_matches_cli_install_instruction():
    from pathlib import Path

    pyproject = (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text(encoding="utf-8")
    assert 'pdfua = ["PyMuPDF>=1.23", "pypdf>=4.0"]' in pyproject


def test_fastapi_uses_lifespan_not_deprecated_on_event():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "docmirror/server/api.py").read_text(encoding="utf-8")
    assert "lifespan=_lifespan" in source
    assert ".on_event(" not in source


def test_mcp_async_tools_offload_sync_sdk_bridge():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "docmirror/server/mcp.py").read_text(encoding="utf-8")
    assert "async def parse_document(" in source
    assert "async def parse_document_from_bytes(" in source
    assert "await asyncio.to_thread(_parse_document_impl" in source
    assert "await asyncio.to_thread(_parse_bytes_impl" in source
