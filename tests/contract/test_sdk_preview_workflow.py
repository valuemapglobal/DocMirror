# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Ensure SDK preview automation builds source without publishing packages."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "publish-sdks.yml"


def test_sdk_preview_workflow_builds_every_advertised_source_preview():
    workflow = yaml.load(WORKFLOW_PATH.read_text(), Loader=yaml.BaseLoader)
    jobs = workflow["jobs"]
    assert {
        "generate-openapi",
        "publish-dmir-schema",
        "generate-typescript",
        "generate-go",
        "generate-java",
        "build-mcp-server",
    } <= set(jobs)

    commands = "\n".join(
        step.get("run", "") for job in jobs.values() for step in job.get("steps", []) if isinstance(step, dict)
    )
    for command in ("npm run typecheck", "go test ./...", "go vet ./...", "mvn -B -ntp verify", "npm pack --dry-run"):
        assert command in commands


def test_sdk_preview_workflow_cannot_publish_or_use_floating_generators():
    text = WORKFLOW_PATH.read_text()
    assert "npm publish" not in text
    assert "mvn deploy" not in text
    assert "@latest" not in text
    assert "openapi-generator-cli" not in text
