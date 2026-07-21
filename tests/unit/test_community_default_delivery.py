# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Fixed delivery contracts across public surfaces."""

from __future__ import annotations

from pathlib import Path

from docmirror.runtime.ledger import build_manifest_v2
from docmirror.runtime.work_units import WorkUnitPlanner
from docmirror.sdk.integration.request import ParseRequest


def test_fixed_delivery_has_no_request_selectors():
    request = ParseRequest()
    manifest = build_manifest_v2("task_default")
    assert not hasattr(request, "formats")
    assert not hasattr(request, "editions")
    assert not hasattr(request, "geometry")
    assert "formats" not in manifest
    assert "editions" not in manifest

    units = WorkUnitPlanner.plan("task_default", "001", "digest", profile="compact")
    projected = [unit.scope["edition"] for unit in units if unit.unit_type == "edition_project"]
    assert projected == ["mirror", "community", "enterprise", "finance"]


def test_delivery_has_no_central_edition_availability_contract():
    root = Path(__file__).resolve().parents[2]
    assert not (root / "docmirror/framework/delivery_contract.py").exists()
    writer_source = (root / "docmirror/server/edition_outputs.py").read_text(encoding="utf-8")
    assert "importlib" not in writer_source
    assert "is_entitled" not in writer_source
