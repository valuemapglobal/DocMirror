# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""CLI four-file write E2E — disk persistence contract (04 redesign)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.tier_e2e, pytest.mark.tier_regression, pytest.mark.integration]

from docmirror.input.entry.factory import PerceiveOptions, perceive_document
from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ResultStatus
from docmirror.server.edition_outputs import write_four_files

LICENSE_FIXTURE = Path("tests/fixtures/business_license/synthetic_medium_variant.pdf")


def test_write_four_files_from_synthetic_mirror(tmp_path: Path):
    mirror = ParseResult(status=ResultStatus.SUCCESS)
    mirror.entities = DocumentEntities(document_type="business_license")

    task_id, written = write_four_files(mirror, tmp_path, file_id="001", task_id="test_task_001")

    assert task_id == "test_task_001"
    assert written["mirror"].name == "001_mirror.json"
    assert written["mirror"].is_file()
    assert written["community"].is_file()

    mirror_data = json.loads(written["mirror"].read_text(encoding="utf-8"))
    comm_data = json.loads(written["community"].read_text(encoding="utf-8"))
    assert mirror_data["source"]["provenance"]["output_ids"]["task_id"] == task_id
    assert comm_data["document"]["document_id"] == f"doc_{task_id}_001"
    assert "editions" not in mirror_data.get("data", {})


def test_write_four_files_respects_requested_editions(tmp_path: Path):
    mirror = ParseResult(status=ResultStatus.SUCCESS)
    mirror.entities = DocumentEntities(document_type="business_license")

    _task_id, written = write_four_files(
        mirror,
        tmp_path,
        file_id="001",
        task_id="test_task_editions",
        editions=("mirror",),
    )

    assert set(written) == {"mirror"}
    assert written["mirror"].is_file()
    assert not (tmp_path / "test_task_editions" / "001_community.json").exists()
    assert not (tmp_path / "test_task_editions" / "manifest.json").exists()


def test_write_four_files_requires_overwrite_for_existing_run_id(tmp_path: Path):
    mirror = ParseResult(status=ResultStatus.SUCCESS)
    mirror.entities = DocumentEntities(document_type="business_license")

    write_four_files(mirror, tmp_path, file_id="001", task_id="test_task_overwrite")

    with pytest.raises(FileExistsError):
        write_four_files(mirror, tmp_path, file_id="001", task_id="test_task_overwrite")

    _task_id, written = write_four_files(
        mirror,
        tmp_path,
        file_id="001",
        task_id="test_task_overwrite",
        overwrite=True,
    )
    assert written["mirror"].is_file()


@pytest.mark.integration
def test_write_four_files_after_perceive(tmp_path: Path):
    if not LICENSE_FIXTURE.is_file():
        pytest.skip(f"missing fixture {LICENSE_FIXTURE}")

    perceive_result = asyncio.run(
        perceive_document(LICENSE_FIXTURE, PerceiveOptions(enhance_mode="standard"))
    )
    result = perceive_result.mirror
    task_id, written = write_four_files(
        result,
        tmp_path,
        file_path=str(LICENSE_FIXTURE),
        full_text=result.full_text,
    )

    assert (tmp_path / task_id / "001_mirror.json").exists()
    mirror_json = json.loads((tmp_path / task_id / "001_mirror.json").read_text(encoding="utf-8"))
    assert mirror_json["source"]["provenance"]["output_ids"]["task_id"] == task_id
    assert mirror_json["document"]["document_id"] == f"doc_{task_id}_001"
    if "community" in written:
        comm_json = json.loads(written["community"].read_text(encoding="utf-8"))
        assert comm_json["metadata"]["task_id"] == task_id
