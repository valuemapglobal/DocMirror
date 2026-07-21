# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Atomic persistence contracts for the projection-only artifact writer."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from docmirror.server.artifact_writer import ArtifactWriter


def test_artifact_writer_atomically_replaces_target(tmp_path):
    writer = ArtifactWriter(tmp_path)
    target = tmp_path / "001_mirror.json"
    target.write_text("old", encoding="utf-8")

    with patch("docmirror.server.artifact_writer.os.replace", wraps=__import__("os").replace) as replace:
        written = writer.write_text(target.name, "new")

    assert written == target
    assert target.read_text(encoding="utf-8") == "new"
    temporary, replaced_target = replace.call_args.args
    assert temporary.parent == tmp_path
    assert temporary.name.startswith(".001_mirror.json.")
    assert replaced_target == target
    assert not temporary.exists()


def test_artifact_writer_cleans_temporary_file_when_replace_fails(tmp_path):
    writer = ArtifactWriter(tmp_path)

    with patch("docmirror.server.artifact_writer.os.replace", side_effect=OSError("replace failed")):
        with pytest.raises(OSError, match="replace failed"):
            writer.write_text("001_mirror.json", "payload")

    assert not (tmp_path / "001_mirror.json").exists()
    assert list(tmp_path.glob(".*.tmp")) == []


def test_artifact_writer_has_no_fact_or_entitlement_dependencies():
    import ast
    import inspect

    import docmirror.server.artifact_writer as module

    source = inspect.getsource(module)
    tree = ast.parse(source)
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    imported_modules.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert not any(name.startswith("docmirror.models") for name in imported_modules)
    assert not any("licens" in name or "entitlement" in name for name in imported_modules)
