# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Contract tests that keep exact-candidate release gates wired into Actions."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _workflow(name: str) -> dict:
    return yaml.load((ROOT / ".github" / "workflows" / name).read_text(), Loader=yaml.BaseLoader)


def test_main_ci_runs_daily_without_cancelling_main_observations():
    workflow = _workflow("ci.yml")
    assert workflow["on"]["schedule"] == [{"cron": "17 2 * * *"}]
    assert workflow["concurrency"]["cancel-in-progress"] == "${{ github.event_name == 'pull_request' }}"


def test_pypi_publish_requires_release_identity_and_exact_commit_ci_gate():
    workflow = _workflow("publish.yml")
    jobs = workflow["jobs"]
    gate = jobs["release-gate"]
    publish = jobs["publish"]
    gate_commands = "\n".join(step.get("run", "") for step in gate["steps"])
    publish_commands = "\n".join(step.get("run", "") for step in publish["steps"])

    assert "GITHUB_REF_NAME" in gate_commands
    assert "git rev-parse origin/main" in gate_commands
    assert "validate_release_commit_ci.py" in gate_commands
    assert "validate_ci_green_window.py" not in gate_commands
    assert "validate_p1_stability_readiness.py --require-qualified" in gate_commands
    assert publish["needs"] == "release-gate"
    assert publish["environment"] == "pypi"
    assert publish["permissions"]["id-token"] == "write"
    assert "pip install build twine pyyaml" in publish_commands
    assert "pip install dist/*.whl" in publish_commands
    assert publish_commands.index("pip install dist/*.whl") < publish_commands.index("validate_oss_release.py")
