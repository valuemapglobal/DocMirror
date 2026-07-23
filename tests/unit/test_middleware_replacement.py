# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Middleware replacements must remain whole canonical transactions."""

import pytest

from docmirror.framework.middlewares.base import BaseMiddleware, MiddlewarePipeline
from docmirror.input.entry.exceptions import MiddlewareError
from docmirror.models.entities.parse_result import DocumentSection, ParseResult


class _ReplacementMiddleware(BaseMiddleware):
    def process(self, result: ParseResult) -> ParseResult:
        replacement = result.model_copy(deep=True)
        replacement.sections = [DocumentSection(id="section_1", title="Facts", name="Facts", page_start=1, page_end=1)]
        replacement.parser_info.warnings.append("replacement-warning")
        replacement.entities.domain_specific["dataset"] = [{"record_id": "row-1"}]
        replacement.record_mutation(
            self.name,
            "parse_result",
            "sections",
            [],
            ["section_1"],
            reason="replace canonical sections",
        )
        replacement.record_mutation(
            self.name,
            "parse_result",
            "entities.domain_specific.dataset",
            None,
            [{"record_id": "row-1"}],
            reason="attach canonical dataset",
        )
        return replacement


class _UnauditedMiddleware(BaseMiddleware):
    def process(self, result: ParseResult) -> ParseResult:
        result.entities.document_type = "unaudited"
        return result


class _LeakingFailureMiddleware(BaseMiddleware):
    def process(self, result: ParseResult) -> ParseResult:
        result.entities.document_type = "partial-leak"
        raise RuntimeError("boom")


def test_pipeline_keeps_all_fields_from_transactional_replacement():
    original = ParseResult()

    result = MiddlewarePipeline().execute([_ReplacementMiddleware()], original)

    assert result is not original
    assert result.sections[0].id == "section_1"
    assert result.parser_info.warnings == ["replacement-warning"]
    assert "step_timings" in result.parser_info.structure
    assert "step_timings" not in result.entities.domain_specific
    assert result.entities.domain_specific["dataset"] == [{"record_id": "row-1"}]
    assert original.sections == []
    assert original.parser_info.warnings == []


def test_pipeline_rejects_unaudited_canonical_change():
    with pytest.raises(MiddlewareError, match="canonical mutation audit gap"):
        MiddlewarePipeline().execute([_UnauditedMiddleware()], ParseResult())


def test_pipeline_aborts_when_failed_middleware_changed_facts():
    with pytest.raises(MiddlewareError, match="failed after changing canonical facts"):
        MiddlewarePipeline().execute([_LeakingFailureMiddleware()], ParseResult())
