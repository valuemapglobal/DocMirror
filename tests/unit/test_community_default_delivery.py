# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Community-only default delivery contracts across public surfaces."""

from __future__ import annotations

from docmirror.framework import edition_defaults
from docmirror.input.entry.options import OutputControl
from docmirror.runtime.ledger import build_manifest_v2
from docmirror.runtime.work_units import WorkUnitPlanner
from docmirror.sdk.integration.request import ParseRequest


def test_community_defaults_are_consistent():
    assert edition_defaults.default_editions() == ("community",)
    assert OutputControl().editions == ("community",)
    assert ParseRequest().editions == ["community"]
    assert build_manifest_v2("task_default")["editions"] == ["community"]

    units = WorkUnitPlanner.plan("task_default", "001", "digest", profile="compact")
    projected = [unit.scope["edition"] for unit in units if unit.unit_type == "edition_project"]
    assert projected == ["community"]


def test_cli_default_adds_mirror_without_changing_programmatic_defaults():
    assert edition_defaults.default_cli_editions() == ("mirror", "community")
    assert edition_defaults.default_editions() == ("community",)
    assert OutputControl().editions == ("community",)


def test_cli_licensed_edition_matrix():
    assert edition_defaults.licensed_cli_editions("community") == ("mirror", "community")
    assert edition_defaults.licensed_cli_editions("enterprise") == ("mirror", "community", "enterprise")
    assert edition_defaults.licensed_cli_editions("finance") == (
        "mirror",
        "community",
        "enterprise",
        "finance",
    )
    assert edition_defaults.licensed_cli_editions("unknown") == ("mirror", "community")
