# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for code hygiene audit helpers."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.code_hygiene.allowlist import is_allowed, load_allowlist
from scripts.code_hygiene.graph import imports_in_file, module_name, resolved_imports_in_file
from scripts.code_hygiene.models import Category, Finding, HygieneReport, Severity
from scripts.code_hygiene.report import format_markdown


def test_module_name():
    path = ROOT / "docmirror" / "core" / "entry" / "factory.py"
    assert module_name(path) == "docmirror.core.entry.factory"


def test_imports_in_file_finds_docmirror():
    path = ROOT / "scripts" / "code_hygiene" / "runner.py"
    imports = resolved_imports_in_file(path)
    assert any("scripts.code_hygiene" in imp for imp in imports)


def test_resolved_relative_import_from_extract_engine():
    from scripts.code_hygiene.graph import resolved_imports_in_file

    path = ROOT / "docmirror" / "core" / "extract" / "engine.py"
    imports = resolved_imports_in_file(path)
    assert "docmirror.core.extract.char_strategy" in imports


def test_module_name_strips_init():
    path = ROOT / "docmirror" / "adapters" / "__init__.py"
    assert module_name(path) == "docmirror.adapters"

def test_allowlist_loads():
    data = load_allowlist()
    assert isinstance(data, dict)


def test_is_allowed_suffix():
    allow = {"orphan_modules": ["hooks.credit_sections"]}
    assert is_allowed("orphan_modules", "docmirror.plugins.post_extract.hooks.credit_sections", allow)


def test_markdown_report_summary():
    from scripts.code_hygiene.models import CheckResult

    report = HygieneReport(
        results=[
            CheckResult(
                name="ruff_strict",
                findings=[
                    Finding(
                        category=Category.UNUSED_IMPORT,
                        severity=Severity.ERROR,
                        message="unused import os",
                        location="docmirror/foo.py:1",
                    )
                ],
            )
        ]
    )
    md = format_markdown(report)
    assert "unused_import" in md
    assert "Errors" in md


def test_commented_blocks_skips_cjk_doc_comments(tmp_path, monkeypatch):
    from scripts.code_hygiene.checks import check_commented_blocks

    sample = tmp_path / "sample.py"
    sample.write_text(
        "\n".join(
            [
                "# 计算置信度: 基于匹配关键词数",
                "# 获取分类目录(如果插件定义了)",
                "# 遍历所有插件",
                "# 默认使用插件域名作为目录",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "scripts.code_hygiene.checks.py_files",
        lambda base: [sample] if sample.parent == base else [],
    )
    monkeypatch.setattr(
        "scripts.code_hygiene.checks.ROOT",
        tmp_path,
    )
    result = check_commented_blocks()
    assert result.findings == []
