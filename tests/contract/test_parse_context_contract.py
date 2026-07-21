# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Contract tests for request-scoped parse context propagation."""

from __future__ import annotations

import asyncio
import importlib
import os
from pathlib import Path

import pytest

from docmirror.framework.base import BaseParser
from docmirror.input.entry.factory import PerceiveOptions, PerceptionFactory, perceive_document
from docmirror.input.entry.options import normalize_parse_policy
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
        self.source = None
        self.policy = None
        self.max_workers = None
        self.on_progress = None

    async def process(self, source, policy, *, max_workers=None, on_progress=None):
        self.source = source
        self.policy = policy
        self.max_workers = max_workers
        self.on_progress = on_progress
        return ParseResult(status=ResultStatus.SUCCESS, pages=[PageContent(page_number=1)])


def test_base_parser_forwards_parse_context_and_fills_provenance(tmp_path: Path, monkeypatch):
    container_module = importlib.import_module("docmirror.framework.di.container")
    monkeypatch.setattr(
        container_module,
        "get_orchestrator",
        lambda: _PassthroughOrchestrator(),
    )
    source = tmp_path / "sample.pdf"
    source.write_bytes(b"%PDF-1.7\n" + b"0" * 128)
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
    from docmirror.configs.format.resolver import resolve_capability
    from docmirror.input import acceptance as acceptance_module
    from docmirror.input.models import AcceptedSource, InputAcceptanceReport

    source = tmp_path / "sample.pdf"
    source.write_bytes(b"%PDF-1.7\n" + b"0" * 128)
    accepted = AcceptedSource(
        path=source,
        original_name=source.name,
        size_bytes=source.stat().st_size,
        detected_mime="application/pdf",
        sha256="test-sha256",
        capability=resolve_capability(source),
        acceptance=InputAcceptanceReport(),
    )
    monkeypatch.setattr(acceptance_module, "accept_source", lambda _path: accepted)
    dispatcher = _CapturingDispatcher()
    monkeypatch.setattr(PerceptionFactory, "get_dispatcher", classmethod(lambda cls: dispatcher))
    monkeypatch.setenv("DOCMIRROR_MAX_PAGES", "77")
    monkeypatch.setenv("DOCMIRROR_ENHANCE_MODE", "standard")

    asyncio.run(
        perceive_document(
            source,
            PerceiveOptions(policy=normalize_parse_policy(max_pages=2, enhance_mode="raw")),
        )
    )

    assert dispatcher.source.path == source
    assert dispatcher.policy.pages.max_pages == 2
    assert dispatcher.policy.enhance_mode == "raw"
    assert dispatcher.max_workers is None
    assert dispatcher.on_progress is None
    assert os.environ["DOCMIRROR_MAX_PAGES"] == "77"
    assert os.environ["DOCMIRROR_ENHANCE_MODE"] == "standard"
