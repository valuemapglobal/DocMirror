# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from click.testing import CliRunner


def test_community_review_summary_exposes_existing_quality_contract(tmp_path):
    import json

    from docmirror.__main__ import _community_review_summary

    output = tmp_path / "001_community.json"
    output.write_text(
        json.dumps(
            {
                "plugin": {"name": "generic"},
                "classification": {"matched_document_type": "audit_report"},
                "quality": {
                    "score": 0.7857,
                    "readiness": "review",
                    "issues": [
                        {"severity": "info", "message": "通用处理"},
                        {"severity": "warning", "message": "复核页55"},
                    ],
                },
                "status": {"warnings": ["a", "b"]},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assert _community_review_summary(output) == {
        "plugin": "generic",
        "document_type": "audit_report",
        "score": 0.7857,
        "readiness": "review",
        "warning_count": 2,
        "review_messages": ["复核页55"],
    }


def test_click_cli_geometry_full_is_canonical(monkeypatch, tmp_path):
    from docmirror.cli.main import parse

    seen = {}

    async def fake_parse_document(*args, **kwargs):
        seen.update(kwargs)

    import docmirror.__main__ as main_mod

    monkeypatch.setattr(main_mod, "parse_document", fake_parse_document)
    src = tmp_path / "sample.txt"
    src.write_text("hello", encoding="utf-8")

    result = CliRunner().invoke(parse, [str(src), "--geometry", "full"])

    assert result.exit_code == 0, result.output
    assert seen["geometry"] == "full"
    assert seen["include_geometry"] is None


def test_click_cli_help_hides_removed_and_advanced_compatibility_options():
    from docmirror.cli.main import parse

    result = CliRunner().invoke(parse, ["--help"])

    assert result.exit_code == 0, result.output
    assert "--mirror" in result.output
    for raw in (
        "--skip-cache",
        "--use-cache",
        "--no-use-cache",
        "--doc-type-hint",
        "--include-geometry",
        "--export-csv",
        "--export-chunks",
        "--editions",
        "--debug-artifact",
        "--mirror-level",
        "--geometry",
        "--split-layers",
        "--include-text",
    ):
        assert raw not in result.output


def test_click_cli_rejects_removed_options(tmp_path):
    from docmirror.cli.main import parse

    src = tmp_path / "sample.txt"
    src.write_text("hello", encoding="utf-8")

    for raw in ("--include-geometry", "--skip-cache", "--doc-type-hint", "--export-csv"):
        result = CliRunner().invoke(parse, [str(src), raw])
        assert result.exit_code != 0
        assert "No such option" in result.output


def test_click_cli_passes_converged_contract_options(monkeypatch, tmp_path):
    from docmirror.cli.main import parse

    seen = {}

    async def fake_parse_document(*args, **kwargs):
        seen.update(kwargs)

    import docmirror.__main__ as main_mod

    monkeypatch.setattr(main_mod, "parse_document", fake_parse_document)
    src = tmp_path / "sample.txt"
    src.write_text("hello", encoding="utf-8")

    result = CliRunner().invoke(
        parse,
        [
            str(src),
            "--cache-policy",
            "refresh",
            "--doc-type",
            "bank_statement",
            "--doc-type-policy",
            "force",
            "--editions",
            "mirror,finance",
            "--ocr",
            "force",
            "--page-split",
            "off",
            "--geometry",
            "full",
            "--mirror-level",
            "compact",
            "--run-id",
            "test_run",
            "--overwrite",
        ],
    )

    assert result.exit_code == 0, result.output
    assert seen["cache_policy"] == "refresh"
    assert seen["doc_type"] == "bank_statement"
    assert seen["doc_type_policy"] == "force"
    assert seen["editions"] == "mirror,finance"
    assert seen["ocr"] == "force"
    assert seen["page_split"] == "off"
    assert seen["geometry"] == "full"
    assert seen["mirror_level"] == "compact"
    assert seen["run_id"] == "test_run"
    assert seen["overwrite"] is True


def test_click_cli_default_editions_are_license_aware(monkeypatch, tmp_path):
    from docmirror.cli.main import parse

    seen = {}

    async def fake_parse_document(*args, **kwargs):
        seen.update(kwargs)

    import docmirror.__main__ as main_mod

    monkeypatch.setattr(main_mod, "parse_document", fake_parse_document)
    src = tmp_path / "sample.txt"
    src.write_text("hello", encoding="utf-8")

    result = CliRunner().invoke(parse, [str(src)])

    assert result.exit_code == 0, result.output
    assert seen["editions"] is None


def test_click_cli_mirror_flag_requests_mirror_and_community(monkeypatch, tmp_path):
    from docmirror.cli.main import parse

    seen = {}

    async def fake_parse_document(*args, **kwargs):
        seen.update(kwargs)

    import docmirror.__main__ as main_mod

    monkeypatch.setattr(main_mod, "parse_document", fake_parse_document)
    src = tmp_path / "sample.txt"
    src.write_text("hello", encoding="utf-8")

    result = CliRunner().invoke(
        parse,
        [str(src), "--mirror"],
    )

    assert result.exit_code == 0, result.output
    assert seen["editions"] == "mirror,community"


def test_click_cli_file_shortcut_keeps_default_editions_unset(monkeypatch, tmp_path):
    from docmirror.cli.main import main

    seen = {}

    async def fake_parse_document(*args, **kwargs):
        seen.update(kwargs)

    import docmirror.__main__ as main_mod

    monkeypatch.setattr(main_mod, "parse_document", fake_parse_document)
    src = tmp_path / "sample.txt"
    src.write_text("hello", encoding="utf-8")

    result = CliRunner().invoke(main, [str(src)])

    assert result.exit_code == 0, result.output
    assert seen["editions"] is None
