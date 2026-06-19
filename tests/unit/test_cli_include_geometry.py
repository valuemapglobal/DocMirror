# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from click.testing import CliRunner


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


def test_click_cli_help_hides_removed_legacy_options():
    from docmirror.cli.main import parse

    result = CliRunner().invoke(parse, ["--help"])

    assert result.exit_code == 0, result.output
    for legacy in (
        "--skip-cache",
        "--use-cache",
        "--no-use-cache",
        "--doc-type-hint",
        "--include-geometry",
        "--export-csv",
        "--export-chunks",
    ):
        assert legacy not in result.output


def test_click_cli_rejects_removed_legacy_options(tmp_path):
    from docmirror.cli.main import parse

    src = tmp_path / "sample.txt"
    src.write_text("hello", encoding="utf-8")

    for legacy in ("--include-geometry", "--skip-cache", "--doc-type-hint", "--export-csv"):
        result = CliRunner().invoke(parse, [str(src), legacy])
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
            "--geometry",
            "full",
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
    assert seen["geometry"] == "full"
    assert seen["run_id"] == "test_run"
    assert seen["overwrite"] is True
