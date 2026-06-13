# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""MEP Golden Track B — Mirror-layer quality gates."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import yaml

from docmirror.configs.paths import MEP_GOLDEN_PROFILES_YAML
from docmirror.core.factory import PerceiveOptions, perceive_document


def _load_profiles() -> dict:
    if not MEP_GOLDEN_PROFILES_YAML.is_file():
        return {}
    with open(MEP_GOLDEN_PROFILES_YAML, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("profiles") or {}


def _check_gate(value, spec: dict) -> bool:
    if "equals" in spec:
        return value == spec["equals"]
    if "in" in spec:
        return value in spec["in"]
    if "min" in spec:
        return value >= spec["min"]
    return True


@pytest.mark.parametrize("profile_name", list(_load_profiles().keys()) or ["__none__"])
def test_mep_golden_profile(profile_name: str):
    profiles = _load_profiles()
    if profile_name == "__none__":
        pytest.skip("no MEP golden profiles configured")
    profile = profiles[profile_name]
    fixture = Path(profile["fixture"])
    if not fixture.is_file():
        pytest.skip(f"fixture missing: {fixture}")

    enhance_mode = profile.get("enhance_mode", "standard")
    perceive_result = asyncio.run(
        perceive_document(fixture, PerceiveOptions(enhance_mode=enhance_mode))
    )
    result = perceive_result.mirror
    gates = profile.get("gates") or {}

    if "document_type" in gates:
        dt = getattr(result.entities, "document_type", "")
        assert _check_gate(dt, gates["document_type"]), f"document_type={dt!r}"

    if "status" in gates:
        status = result.status.value if hasattr(result.status, "value") else str(result.status)
        assert _check_gate(status, gates["status"]), f"status={status!r}"

    if "page_count" in gates:
        assert _check_gate(result.page_count, gates["page_count"])

    if "table_count" in gates:
        assert _check_gate(result.total_tables, gates["table_count"])
