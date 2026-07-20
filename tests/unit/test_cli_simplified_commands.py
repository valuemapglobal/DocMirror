# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from click.testing import CliRunner


def test_top_level_license_defaults_to_show():
    from docmirror.cli.main import main

    result = CliRunner().invoke(main, ["license"])

    assert result.exit_code == 0, result.output
    assert "License Snapshot" in result.output or "No active license" in result.output


def test_plugins_without_subcommand_defaults_to_list():
    from docmirror.cli.main import main

    result = CliRunner().invoke(main, ["plugins"])

    assert result.exit_code == 0, result.output
    assert "Plugins (" in result.output


def test_plugins_ls_alias_keeps_list_command():
    from docmirror.cli.main import main

    result = CliRunner().invoke(main, ["plugins", "ls", "--format", "json"])

    assert result.exit_code == 0, result.output
    assert result.output.lstrip().startswith("[")


def test_short_ocr_command_is_the_only_ocr_entrypoint():
    from docmirror.cli.main import main

    runner = CliRunner()
    short = runner.invoke(main, ["ocr", "check"])
    legacy = runner.invoke(main, ["ocr-correction", "validate"])

    assert short.exit_code == 0, short.output
    assert legacy.exit_code != 0
    assert "correction pack(s) are valid" in short.output
    assert "No such command 'ocr-correction'" in legacy.output


def test_short_ocr_aliases_are_discoverable():
    from docmirror.cli.main import main

    result = CliRunner().invoke(main, ["ocr", "--help"])

    assert result.exit_code == 0, result.output
    for command in ("check", "packs", "eval", "export"):
        assert command in result.output


def test_removed_nested_license_and_plugin_list_commands_are_rejected():
    from docmirror.cli.main import main

    runner = CliRunner()
    nested_license = runner.invoke(main, ["plugins", "license", "show"])
    old_list = runner.invoke(main, ["plugins", "list"])

    assert nested_license.exit_code != 0
    assert "No such command 'license'" in nested_license.output
    assert old_list.exit_code != 0
    assert "No such command 'list'" in old_list.output
