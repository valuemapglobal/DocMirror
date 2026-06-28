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
from scripts.code_hygiene.graph import imports_in_file, module_name, patch_literals_in_file, resolved_imports_in_file
from scripts.code_hygiene.models import Category, Finding, HygieneReport, Severity
from scripts.code_hygiene.report import format_markdown
from scripts.validate.generate_import_linter import render_import_linter


def test_module_name():
    path = ROOT / "docmirror" / "input" / "entry" / "factory.py"
    assert module_name(path) == "docmirror.input.entry.factory"


def test_imports_in_file_finds_docmirror():
    path = ROOT / "scripts" / "code_hygiene" / "runner.py"
    imports = resolved_imports_in_file(path)
    assert any("scripts.code_hygiene" in imp for imp in imports)


def test_resolved_relative_import_from_extract_engine():
    from scripts.code_hygiene.graph import resolved_imports_in_file

    path = ROOT / "docmirror" / "structure" / "tables" / "engine.py"
    imports = resolved_imports_in_file(path)
    assert "docmirror.structure.tables.char_strategy" in imports


def test_patch_literals_are_import_references(tmp_path):
    sample = tmp_path / "sample.py"
    sample.write_text(
        'from unittest.mock import patch\n'
        'with patch("docmirror.plugins._runtime.runner._edition_package_available"):\n'
        '    pass\n',
        encoding="utf-8",
    )

    assert patch_literals_in_file(sample) == [
        "docmirror.plugins._runtime.runner._edition_package_available"
    ]


def test_module_name_strips_init():
    path = ROOT / "docmirror" / "input" / "adapters" / "__init__.py"
    assert module_name(path) == "docmirror.input.adapters"


def test_allowlist_loads():
    data = load_allowlist()
    assert isinstance(data, dict)


def test_is_allowed_suffix():
    allow = {"orphan_modules": ["hooks.credit_sections"]}
    assert is_allowed("orphan_modules", "docmirror.plugins._runtime.post_extract.hooks.credit_sections", allow)


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


def test_import_linter_rendered_from_manifest_layers():
    rendered = render_import_linter(
        {
            "external_modules": [{"regex": r"^typing\.*"}],
            "layers": {
                "models": {
                    "paths": ["docmirror/models/**"],
                    "forbidden_imports": ["docmirror.input", "docmirror.output"],
                    "import_linter_allow_indirect": True,
                    "import_linter_ignore_imports": [
                        {
                            "importer": "docmirror.models.bridge",
                            "imported": "docmirror.input.bridge",
                            "reason": "legacy",
                            "review_by": "2026-08-01",
                        }
                    ],
                },
                "runtime": {"paths": ["docmirror/runtime/**"]},
            },
        }
    )

    assert "[importlinter]" in rendered
    assert "root_package = docmirror" in rendered
    assert "[importlinter:manifest_forbidden_1_models]" in rendered
    assert "    docmirror.models" in rendered
    assert "    docmirror.input" in rendered
    assert "allow_indirect_imports = True" in rendered
    assert "    docmirror.models.bridge -> docmirror.input.bridge" in rendered
    assert "docmirror.runtime" not in rendered


def test_clean_quarantine_report_classifies_review_dates(monkeypatch):
    from datetime import date
    from types import SimpleNamespace

    from scripts.validate import report_clean_quarantine

    monkeypatch.setattr(
        report_clean_quarantine,
        "load_clean_manifest",
        lambda: SimpleNamespace(
            data={
                "quarantine_modules": [
                    {
                        "module": "docmirror.old",
                        "owner": "core",
                        "reason": "old",
                        "exit_criteria": "delete",
                        "review_by": "2026-06-01",
                    },
                    {
                        "module": "docmirror.soon",
                        "owner": "core",
                        "reason": "soon",
                        "exit_criteria": "decide",
                        "review_by": "2026-07-10",
                    },
                    {
                        "module": "docmirror.later",
                        "owner": "core",
                        "reason": "later",
                        "exit_criteria": "retain",
                        "review_by": "2026-08-01",
                    },
                ]
            }
        ),
    )

    report = report_clean_quarantine.build_report(today=date(2026, 6, 28))

    assert report["counts"] == {"overdue": 1, "due_soon": 1, "scheduled": 1}
    assert [item["module"] for item in report["items"]] == [
        "docmirror.old",
        "docmirror.soon",
        "docmirror.later",
    ]
