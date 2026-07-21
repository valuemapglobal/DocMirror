# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Public CLI contract tests for OSS release readiness."""

from __future__ import annotations

from click.testing import CliRunner

from docmirror import __version__
from docmirror.cli.main import main


def test_cli_help_is_light_and_positioned():
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0, result.output
    assert "The Trust Layer for Commercial Documents" in result.output
    assert "Parse. Prove. Trust." in result.output


def test_cli_short_version_flag():
    result = CliRunner().invoke(main, ["-v"])
    assert result.exit_code == 0, result.output
    assert __version__ in result.output


def test_cli_doctor_command():
    result = CliRunner().invoke(main, ["doctor"])
    assert result.exit_code == 0, result.output
    assert "Commercial Document Trust Layer" in result.output
    assert "- core:" in result.output


def test_cli_root_file_routes_to_document_help():
    result = CliRunner().invoke(main, ["sample.pdf", "--help"])
    assert result.exit_code == 0, result.output
    assert "Parse a document" in result.output
    assert "--output-dir" in result.output
