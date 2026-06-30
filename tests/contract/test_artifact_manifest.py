# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path

from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ResultStatus
from docmirror.server.edition_outputs import write_four_files
from docmirror.server.task_result import task_result_from_manifest


def test_write_four_files_writes_artifact_manifest(tmp_path: Path):
    mirror = ParseResult(status=ResultStatus.SUCCESS)
    mirror.entities = DocumentEntities(document_type="business_license")

    task_id, written = write_four_files(
        mirror,
        tmp_path,
        file_id="001",
        task_id="task_manifest",
        editions=("mirror", "community", "enterprise", "finance"),
        artifact_pack=True,
    )

    manifest_path = tmp_path / task_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    task = task_result_from_manifest(manifest_path)

    assert written["mirror"].name == "001_mirror.json"
    assert manifest["artifacts"]["mirror"] == "001_mirror.json"
    assert manifest["edition_availability"]["enterprise"]["status"] in {"unavailable", "written", "skipped"}
    assert "mirror_completeness" in manifest
    assert task.task_id == "task_manifest"
