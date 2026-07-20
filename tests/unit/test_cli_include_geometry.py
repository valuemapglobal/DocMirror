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
    for raw in ("-p, --pages", "-t, --doc-type", "-r, --recursive", "-q, --quiet", "--all", "--audit"):
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
    ):
        assert raw not in result.output


def test_click_cli_help_all_shows_advanced_options():
    from docmirror.cli.main import main

    result = CliRunner().invoke(main, ["--help-all"])

    assert result.exit_code == 0, result.output
    assert "Advanced parse options:" in result.output
    for raw in ("--mirror-level", "--geometry", "--cache-policy", "--ocr-correction-pack"):
        assert raw in result.output
    for removed in ("--profile", "--editions", "\n  --mirror ", "--debug-artifact", "--log-level"):
        assert removed not in result.output


def test_click_cli_short_version_flag():
    from docmirror.cli.main import main

    result = CliRunner().invoke(main, ["-v"])

    assert result.exit_code == 0, result.output
    assert "1.0.8" in result.output


def test_click_cli_rejects_removed_options(tmp_path):
    from docmirror.cli.main import parse

    src = tmp_path / "sample.txt"
    src.write_text("hello", encoding="utf-8")

    for raw in (
        "--include-geometry",
        "--skip-cache",
        "--doc-type-hint",
        "--export-csv",
        "--mirror",
        "--profile",
        "--editions",
        "--debug-artifact",
        "--split-layers",
        "--log-level",
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
            "--cache-policy",
            "refresh",
            "--doc-type",
            "bank_statement",
            "--doc-type-policy",
            "force",
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
    assert seen["editions"] == ("mirror", "community")
    assert seen["ocr"] == "force"
    assert seen["page_split"] == "off"
    assert seen["geometry"] == "full"
    assert seen["mirror_level"] == "compact"
    assert seen["run_id"] == "test_run"
    assert seen["overwrite"] is True


def test_click_cli_default_editions_include_mirror_and_community(monkeypatch, tmp_path):
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
    assert seen["editions"] == ("mirror", "community")


def test_click_cli_file_shortcut_writes_mirror_and_community(monkeypatch, tmp_path):
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
    assert seen["editions"] == ("mirror", "community")


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


def test_click_cli_all_uses_highest_licensed_installed_edition(monkeypatch, tmp_path):
    from docmirror.cli.main import parse
    from docmirror.plugins._runtime.licensing import entitlements

    seen = {}

    async def fake_parse_document(*args, **kwargs):
        seen.update(kwargs)

    import docmirror.__main__ as main_mod

    monkeypatch.setattr(main_mod, "parse_document", fake_parse_document)
    monkeypatch.setattr(entitlements, "resolve_edition_tier", lambda: "finance")
    src = tmp_path / "sample.txt"
    src.write_text("hello", encoding="utf-8")

    result = CliRunner().invoke(parse, [str(src), "--all"])

    assert result.exit_code == 0, result.output
    assert seen["editions"] == ("mirror", "community", "enterprise", "finance")
    assert seen["debug_artifact"] is False


def test_click_cli_audit_uses_licensed_editions_and_forensic_artifacts(monkeypatch, tmp_path):
    from docmirror.cli.main import parse
    from docmirror.plugins._runtime.licensing import entitlements

    seen = {}

    async def fake_parse_document(*args, **kwargs):
        seen.update(kwargs)

    import docmirror.__main__ as main_mod

    monkeypatch.setattr(main_mod, "parse_document", fake_parse_document)
    monkeypatch.setattr(entitlements, "resolve_edition_tier", lambda: "enterprise")
    src = tmp_path / "sample.txt"
    src.write_text("hello", encoding="utf-8")

    result = CliRunner().invoke(parse, [str(src), "--audit"])

    assert result.exit_code == 0, result.output
    assert seen["editions"] == ("mirror", "community", "enterprise")
    assert seen["debug_artifact"] is True
    assert seen["mirror_level"] == "forensic"
    assert seen["geometry"] == "full"


def test_click_cli_community_shortcut_is_community_only(monkeypatch, tmp_path):
    from docmirror.cli.main import parse

    seen = {}

    async def fake_parse_document(*args, **kwargs):
        seen.update(kwargs)

    import docmirror.__main__ as main_mod

    monkeypatch.setattr(main_mod, "parse_document", fake_parse_document)
    src = tmp_path / "sample.txt"
    src.write_text("hello", encoding="utf-8")

    result = CliRunner().invoke(parse, [str(src), "--community"])

    assert result.exit_code == 0, result.output
    assert seen["editions"] == ("community",)


def test_click_cli_rejects_conflicting_output_shortcuts(tmp_path):
    from docmirror.cli.main import parse

    src = tmp_path / "sample.txt"
    src.write_text("hello", encoding="utf-8")

    result = CliRunner().invoke(parse, [str(src), "--all", "--community"])

    assert result.exit_code != 0
    assert "output selectors are mutually exclusive" in result.output


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
