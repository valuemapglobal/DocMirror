# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""The 2.0 compatibility-retirement register must describe a clean runtime."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
REGISTER = ROOT / "docmirror" / "configs" / "architecture" / "compatibility_retirement.yaml"


def _load_register() -> dict:
    return yaml.safe_load(REGISTER.read_text(encoding="utf-8")) or {}


def test_runtime_has_no_compatibility_only_surface_or_module() -> None:
    register = _load_register()

    assert register["version"] == 2
    assert register["surfaces"] == []
    assert register["compatibility_only_modules"] == []


def test_retired_surface_history_is_unique_and_actionable() -> None:
    retired = _load_register()["retired_surfaces"]
    symbols = [item["symbol"] for item in retired]

    assert len(symbols) == len(set(symbols))
    assert symbols
    assert all(item["owner"] and item["replacement"] for item in retired)


def test_retired_python_surfaces_are_not_reachable() -> None:
    from docmirror.models.sealed import SealedParseResult
    from docmirror.plugin_api import __all__ as plugin_api_exports
    from docmirror.sdk.integration.request import ParseRequest
    from docmirror.server import output_builder

    assert "DomainPlugin" not in plugin_api_exports
    assert not hasattr(output_builder, "build_community_output")
    assert not hasattr(output_builder, "build_api_response")
    assert not hasattr(SealedParseResult, "to_legacy_copy")
    assert "input" not in ParseRequest.__dataclass_fields__
    assert "sync" not in ParseRequest.__dataclass_fields__


def test_production_does_not_reference_retired_execution_paths() -> None:
    forbidden = ("build_community_output", "run_plugin_extract_sync", "post_extract")
    offenders = []
    for path in (ROOT / "docmirror").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if any(token in source for token in forbidden):
            offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []
