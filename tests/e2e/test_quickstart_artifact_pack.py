# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path

from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ResultStatus
from docmirror.server.edition_outputs import write_four_files


def test_quickstart_artifact_pack_written(tmp_path: Path):
    mirror = ParseResult(status=ResultStatus.SUCCESS)
    mirror.entities = DocumentEntities(document_type="business_license")
    task_id, _written = write_four_files(
        mirror,
        tmp_path,
        file_id="001",
        task_id="quickstart_pack",
        editions=("mirror", "community"),
        profile="ga_full",
    )

    task_dir = tmp_path / task_id
    manifest = json.loads((task_dir / "manifest.json").read_text(encoding="utf-8"))

    assert (task_dir / "quality_report.json").is_file()
    assert (task_dir / "visual_debug.html").is_file()
    assert (task_dir / "evidence").is_dir()
    assert (task_dir / "output.md").is_file()
    assert manifest["artifacts"]["quality_report"] == "quality_report.json"
    assert manifest["artifacts"]["visual_debug"] == "visual_debug.html"
    assert "open_source_commitment" in manifest
    assert "domain_readiness" in manifest
