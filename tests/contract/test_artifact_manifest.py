# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path

from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ResultStatus
from docmirror.server.edition_outputs import write_outputs
from docmirror.server.task_result import task_result_from_manifest


def test_write_outputs_writes_artifact_manifest(tmp_path: Path):
    mirror = ParseResult(status=ResultStatus.SUCCESS)
    mirror.entities = DocumentEntities(document_type="business_license")

    task_id, written = write_outputs(
        mirror,
        tmp_path,
        file_id="001",
        task_id="task_manifest",
    )

    manifest_path = tmp_path / task_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    task = task_result_from_manifest(manifest_path)

    assert written["mirror"].name == "001_mirror.json"
    assert manifest["artifacts"]["mirror"] == "001_mirror.json"
    assert manifest["artifacts"] == {edition: path.name for edition, path in written.items()}
    for edition in ("mirror", "community", "enterprise", "finance"):
        expected = "written" if edition in written else "unavailable"
        assert manifest["edition_availability"][edition]["status"] == expected
    assert "dmir" not in manifest["artifacts"]
    assert "license_state" not in json.dumps(manifest)
    assert "mirror_completeness" in manifest
    assert task.task_id == "task_manifest"
