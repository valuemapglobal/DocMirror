# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the table method registry migration."""

from __future__ import annotations

from types import SimpleNamespace

from docmirror.structure.tables.engine import extract_tables_layered
from docmirror.structure.tables.method_reconstructor import (
    TableMethodReconstructor,
    TableMethodRegistry,
)

EXPECTED_METHOD_IDS = {
    "pipe_delimited",
    "pymupdf_native",
    "pdfplumber_default",
    "lines",
    "hline_columns",
    "rect_columns",
    "text",
    "text_fallback",
    "header_anchors",
    "header_guided",
    "grid_reconstructor",
    "word_anchors",
    "data_voting",
    "whitespace_projection",
    "x_clustering",
    "signal_processor",
    "rapid_table",
    "template_injection",
}


class FakePdfPlumberPage:
    width = 612
    height = 792
    chars: list[dict] = []
    lines: list[dict] = []
    rects: list[dict] = []

    def extract_text(self) -> str:
        return "Date Amount Balance"

    def extract_tables(self, table_settings=None):
        if table_settings is not None:
            return []
        return [[["Date", "Amount", "Balance"], ["2026-06-01", "12.30", "100.00"]]]


class WorkingMethod(TableMethodReconstructor):
    id = "working"
    supported_layers = {"native"}

    def score(self, page_plum, profile=None, context=None):
        return 0.7

    def reconstruct(self, page_plum, profile=None, context=None):
        return [["A", "B"], ["1", "2"]]


class FailingMethod(TableMethodReconstructor):
    id = "failing"
    supported_layers = {"native"}

    def reconstruct(self, page_plum, profile=None, context=None):
        raise RuntimeError("intentional test failure")


def test_builtin_table_method_registry_covers_all_migrated_methods():
    registry = TableMethodRegistry()

    assert set(registry.list_ids()) == EXPECTED_METHOD_IDS
    assert len(registry.list_ids()) == 18


def test_table_method_registry_dispatch_isolates_method_failures():
    registry = TableMethodRegistry([FailingMethod(), WorkingMethod()])

    results = registry.reconstruct_all(FakePdfPlumberPage(), layers={"native"})

    assert results == [("working", [["A", "B"], ["1", "2"]], 0.7)]


def test_extract_tables_layered_uses_registry_path_when_feature_flag_enabled(monkeypatch):
    import docmirror.configs.runtime.settings as runtime_settings

    monkeypatch.setattr(
        runtime_settings,
        "get_settings",
        lambda: SimpleNamespace(udtr_use_table_method_registry=True),
    )

    tables, layer, confidence = extract_tables_layered(FakePdfPlumberPage())

    assert layer == "pdfplumber_default"
    assert tables == [[["Date", "Amount", "Balance"], ["2026-06-01", "12.30", "100.00"]]]
    assert confidence > 0
