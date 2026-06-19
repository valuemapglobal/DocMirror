# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.

import pytest
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from docmirror.framework.cache import ParseCache
from docmirror.core.entry.options import normalize_parse_control
from docmirror.models.entities.parse_result import ParseResult


@pytest.mark.asyncio
async def test_parse_cache_set_and_get():
    # Setup mock Redis client
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value="{\"status\": \"success\", \"parser_info\": {\"parser_name\": \"test\"}}")
    mock_redis.setex = AsyncMock(return_value=True)
    mock_redis.ping = AsyncMock(return_value=True)

    cache = ParseCache()
    # Mock connection lazily returning mock_redis
    with patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379"}):
        with patch.object(cache, "_get_redis", return_value=mock_redis):
            # Test key format
            key = cache._key("my_checksum", "my_fingerprint")
            assert key == "parse:my_checksum:my_fingerprint"

            # Test get
            val = await cache.get("my_checksum", "my_fingerprint")
            assert val is not None
            assert "success" in val
            mock_redis.get.assert_called_with(key)

            # Test set
            ok = await cache.set("my_checksum", "my_fingerprint", "dummy_json")
            assert ok is True
            mock_redis.setex.assert_called_with(key, 86400, "dummy_json")


@pytest.mark.asyncio
async def test_dispatcher_cache_bypass_when_skip_cache():
    from docmirror.framework.dispatcher import ParserDispatcher, FileContext

    dispatcher = ParserDispatcher()
    
    # Mock _validate and resolve_capability
    dummy_ctx = FileContext(
        path=Path("dummy.pdf"),
        file_type="pdf",
        content_model="fixed_layout",
        capability_id="pdf_native",
        capability_status="supported",
        file_size=100,
        mime_type="application/pdf",
        checksum="dummy_checksum",
        is_forged=False,
        forgery_reasons=[],
    )
    
    dummy_cap = MagicMock()
    dummy_cap.status = "supported"
    dummy_cap.transport = "pdf"
    dummy_cap.content_model = "fixed_layout"
    dummy_cap.id = "pdf_native"

    with patch.object(dispatcher, "_validate", return_value=dummy_ctx):
        with patch("docmirror.framework.dispatcher.resolve_capability", return_value=dummy_cap):
            # Mock ParseCache singleton methods
            with patch("docmirror.framework.cache.parse_cache.get", AsyncMock(return_value=None)) as mock_get:
                # 1. With skip_cache=True
                control_skip = normalize_parse_control(skip_cache=True)
                # Mock run_extraction_chain to return a dummy result
                dummy_result = MagicMock()
                dummy_result.success = True
                dummy_result.parser_info.parser_name = "test"
                dummy_result.full_text = "test"
                dummy_result.total_tables = 0
                dummy_result.status.value = "success"

                with patch("docmirror.framework.dispatcher.run_extraction_chain", AsyncMock(return_value=dummy_result)):
                    await dispatcher.process(
                        file_path="dummy.pdf",
                        skip_cache=True,
                        parse_control=control_skip,
                    )
                    mock_get.assert_not_called()

                # 2. With skip_cache=False (should query cache)
                control_use = normalize_parse_control(skip_cache=False)
                mock_get.reset_mock()
                with patch("docmirror.framework.dispatcher.run_extraction_chain", AsyncMock(return_value=dummy_result)):
                    with patch("docmirror.framework.cache.parse_cache.set", AsyncMock(return_value=True)):
                        await dispatcher.process(
                            file_path="dummy.pdf",
                            skip_cache=False,
                            parse_control=control_use,
                        )
                        mock_get.assert_called_once()


def test_argparse_cache_options():
    import sys
    from docmirror.__main__ import main

    test_args = ["docmirror", "dummy.pdf", "--no-use-cache"]
    with patch.object(sys, "argv", test_args):
        with patch("docmirror.__main__.parse_document", AsyncMock()) as mock_parse:
            with patch("pathlib.Path.exists", return_value=True):
                with patch("pathlib.Path.is_dir", return_value=False):
                    main()
                    mock_parse.assert_called_once()
                    # Positional or keyword arguments
                    args = mock_parse.call_args[0]
                    # args is (file_path, format, output_dir, no_save, skip_cache, ...)
                    # skip_cache is the 5th positional argument (index 4)
                    assert args[4] is True

