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


def test_community_review_summary_ignores_informational_fallback(tmp_path):
    import json

    from docmirror.__main__ import _community_review_summary

    output = tmp_path / "001_community.json"
    output.write_text(
        json.dumps(
            {
                "schema": {"name": "docmirror.community", "support_level": "generic", "domain": "id_card"},
                "document": {"type": "id_card"},
                "warnings": [
                    {
                        "code": "COMMUNITY_GENERIC_FALLBACK",
                        "level": "info",
                        "message": "community_generic_fallback",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    assert _community_review_summary(output) == {
        "plugin": "generic",
        "document_type": "id_card",
        "score": 1.0,
        "readiness": "ready",
        "warning_count": 0,
        "review_messages": [],
    }


def test_click_cli_help_hides_removed_and_advanced_compatibility_options():
    from docmirror.cli.main import parse

    result = CliRunner().invoke(parse, ["--help"])

    assert result.exit_code == 0, result.output
    for raw in ("-p, --pages", "-t, --doc-type", "-r, --recursive", "-q, --quiet"):
        assert raw in result.output
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
        "--mirror",
        "--profile",
        "--cache-policy",
        "--ocr-correction-pack",
        "--log-level",
        "--format",
        "--audit",
        "--community",
    ):
        assert raw not in result.output


def test_click_cli_help_all_shows_advanced_options():
    from docmirror.cli.main import main

    result = CliRunner().invoke(main, ["--help-all"])

    assert result.exit_code == 0, result.output
    assert "Advanced parse options:" in result.output
    assert "--ocr-correction-pack" in result.output
    for removed in (
        "--profile",
        "--editions",
        "\n  --mirror ",
        "--debug-artifact",
        "--cache-policy",
        "--log-level",
        "--mirror-level",
        "--geometry",
        "--include-text",
        "--format",
        "--audit",
        "--community",
    ):
        assert removed not in result.output


def test_click_cli_short_version_flag():
    from docmirror.cli.main import main

    result = CliRunner().invoke(main, ["-v"])

    assert result.exit_code == 0, result.output
    assert "1.0.10" in result.output


def test_click_cli_rejects_removed_options(tmp_path):
    from docmirror.cli.main import parse

    src = tmp_path / "sample.txt"
    src.write_text("hello", encoding="utf-8")

    for raw in (
        "--include-geometry",
        "--skip-cache",
        "--cache-policy",
        "--doc-type-hint",
        "--export-csv",
        "--mirror",
        "--profile",
        "--editions",
        "--debug-artifact",
        "--split-layers",
        "--log-level",
        "--mirror-level",
        "--geometry",
        "--include-text",
        "--format",
        "--audit",
        "--community",
    ):
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
            "--doc-type",
            "bank_statement",
            "--doc-type-policy",
            "force",
            "--ocr",
            "force",
            "--page-split",
            "off",
            "--run-id",
            "test_run",
            "--overwrite",
        ],
    )

    assert result.exit_code == 0, result.output
    assert seen["doc_type"] == "bank_statement"
    assert seen["doc_type_policy"] == "force"
    assert seen["ocr"] == "force"
    assert seen["page_split"] == "off"
    assert set(seen).isdisjoint({"formats", "editions", "geometry", "mirror_level", "include_text"})
    assert seen["run_id"] == "test_run"
    assert seen["overwrite"] is True


def test_click_cli_has_no_output_selection_arguments(monkeypatch, tmp_path):
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
    assert set(seen).isdisjoint({"formats", "editions", "geometry", "mirror_level", "include_text"})
    assert seen["all_outputs"] is False


def test_click_cli_all_enables_support_outputs(monkeypatch, tmp_path):
    from docmirror.cli.main import parse

    seen = {}

    async def fake_parse_document(*args, **kwargs):
        seen.update(kwargs)

    import docmirror.__main__ as main_mod

    monkeypatch.setattr(main_mod, "parse_document", fake_parse_document)
    src = tmp_path / "sample.txt"
    src.write_text("hello", encoding="utf-8")

    for option in ("--all", "-all"):
        seen.clear()
        result = CliRunner().invoke(parse, [str(src), option])
        assert result.exit_code == 0, result.output
        assert seen["all_outputs"] is True


def test_click_cli_file_shortcut_has_fixed_delivery(monkeypatch, tmp_path):
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
    assert set(seen).isdisjoint({"formats", "editions", "geometry", "mirror_level", "include_text"})


def test_click_cli_short_parse_options(monkeypatch, tmp_path):
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
        [str(src), "-p", "1-2", "-m", "fast", "-t", "credit_report", "-j", "2", "-q"],
    )

    assert result.exit_code == 0, result.output
    assert seen["pages"] == "1-2"
    assert seen["mode"] == "fast"
    assert seen["doc_type"] == "credit_report"
    assert seen["workers"] == "2"


def test_click_cli_rejects_conflicting_verbosity(tmp_path):
    from docmirror.cli.main import parse

    src = tmp_path / "sample.txt"
    src.write_text("hello", encoding="utf-8")

    result = CliRunner().invoke(parse, [str(src), "--quiet", "--verbose"])

    assert result.exit_code != 0
    assert "--quiet and --verbose are mutually exclusive" in result.output


def test_root_cli_rejects_removed_parse_and_version_commands():
    from docmirror.cli.main import main

    runner = CliRunner()
    parse_result = runner.invoke(main, ["parse", "sample.pdf"])
    version_result = runner.invoke(main, ["version"])

    assert parse_result.exit_code != 0
    assert "parse subcommand was removed" in parse_result.output
    assert version_result.exit_code != 0
    assert "No such command 'version'" in version_result.output
