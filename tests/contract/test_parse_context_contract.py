# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Contract tests for request-scoped parse context propagation."""

from __future__ import annotations

import asyncio
import importlib
import os
from pathlib import Path

import pytest

from docmirror.core.entry.factory import PerceiveOptions, PerceptionFactory, perceive_document
from docmirror.framework.base import BaseParser
from docmirror.models.entities.parse_result import PageContent, ParseResult, ResultStatus

pytestmark = [pytest.mark.tier_contract]


class _PassthroughOrchestrator:
    async def enhance(self, result: ParseResult, **kwargs) -> ParseResult:
        result.entities.domain_specific["enhance_kwargs"] = kwargs
        return result


class _ContextCapturingParser(BaseParser):
    def __init__(self) -> None:
        self.context: dict = {}

    async def to_parse_result(self, file_path: Path, **kwargs) -> ParseResult:
        self.context = kwargs
        return ParseResult(
            status=ResultStatus.SUCCESS,
            pages=[PageContent(page_number=1)],
        )


class _CapturingDispatcher:
    def __init__(self) -> None:
        self.kwargs: dict = {}

    async def process(self, file_path, **kwargs):
        self.kwargs = kwargs
        return ParseResult(status=ResultStatus.SUCCESS, pages=[PageContent(page_number=1)])


def test_base_parser_forwards_parse_context_and_fills_provenance(tmp_path: Path, monkeypatch):
    container_module = importlib.import_module("docmirror.di.container")
    monkeypatch.setattr(
        container_module,
        "get_orchestrator",
        lambda: _PassthroughOrchestrator(),
    )
    source = tmp_path / "sample.pdf"
    source.write_bytes(b"%PDF-1.7\n")
    parser = _ContextCapturingParser()

    result = asyncio.run(
        parser.perceive(
            source,
            file_type="pdf",
            content_model="page_layout",
            capability_id="pdf_text",
            file_size=123,
            checksum="fast:123:456:abcdef01",
            mime_type="application/pdf",
            enhance_mode="raw",
        )
    )

    assert parser.context["checksum"] == "fast:123:456:abcdef01"
    assert parser.context["content_model"] == "page_layout"
    assert result.provenance is not None
    assert result.provenance.file_type == "pdf"
    assert result.provenance.file_size == 123
    assert result.provenance.checksum == "fast:123:456:abcdef01"
    assert result.provenance.mime_type == "application/pdf"
    assert result.provenance.capability_id == "pdf_text"
    assert result.provenance.content_model == "page_layout"
    assert result.entities.domain_specific["enhance_kwargs"]["enhance_mode"] == "raw"


def test_perceive_options_do_not_mutate_process_env(tmp_path: Path, monkeypatch):
    source = tmp_path / "sample.pdf"
    source.write_bytes(b"%PDF-1.7\n")
    dispatcher = _CapturingDispatcher()
    monkeypatch.setattr(PerceptionFactory, "get_dispatcher", classmethod(lambda cls: dispatcher))
    monkeypatch.setenv("DOCMIRROR_MAX_PAGES", "77")
    monkeypatch.setenv("DOCMIRROR_ENHANCE_MODE", "standard")

    asyncio.run(
        perceive_document(
            source,
            PerceiveOptions(max_pages=2, enhance_mode="raw"),
        )
    )

    assert dispatcher.kwargs["max_pages"] == 2
    assert dispatcher.kwargs["enhance_mode"] == "raw"
    assert dispatcher.kwargs["skip_cache"] is False
    assert dispatcher.kwargs["on_progress"] is None
    assert os.environ["DOCMIRROR_MAX_PAGES"] == "77"
    assert os.environ["DOCMIRROR_ENHANCE_MODE"] == "standard"
