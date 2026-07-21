# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Fixed CLI delivery persistence contract."""

from __future__ import annotations

import asyncio
import csv
import io
import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.tier_e2e, pytest.mark.tier_regression, pytest.mark.integration]

from docmirror.input.entry.factory import PerceiveOptions, perceive_document
from docmirror.input.entry.options import normalize_parse_policy
from docmirror.models.entities.parse_result import DocumentEntities, PageContent, ParseResult, ResultStatus, TextBlock
from docmirror.models.schemas.registry import validate_projection_payload
from docmirror.server.edition_outputs import write_outputs
from scripts.validate.validate_community_artifacts import validate_community_artifacts

LICENSE_FIXTURE = Path("tests/fixtures/business_license/synthetic_medium_variant.pdf")


def test_write_outputs_uses_fixed_delivery(tmp_path: Path):
    result = ParseResult(status=ResultStatus.SUCCESS)
    result.entities = DocumentEntities(
        document_type="business_license",
        domain_specific={
            "records": [
                {"record_id": "license:001", "normalized": {"field": "A"}, "raw": {"field": "原值A"}},
                {"record_id": "license:002", "normalized": {"field": "B"}, "raw": {"field": "原值B"}},
            ]
        },
    )

    task_id, written = write_outputs(result, tmp_path, file_id="001", task_id="test_task_001")

    assert task_id == "test_task_001"
    assert {"mirror", "community", "content", "datasets"} <= set(written)
    assert written["community"].is_file()
    assert written["content"].name == "001_content.md"
    assert written["datasets"].name == "001_datasets"
    assert written["datasets"].is_dir()
    assert (written["datasets"] / "_audit_cells.csv").is_file()
    assert (tmp_path / task_id / "001_mirror.json").exists()
    assert (tmp_path / task_id / "manifest.json").exists()

    comm_data = json.loads(written["community"].read_text(encoding="utf-8"))
    assert comm_data["schema"]["version"] == "3.0.0"
    assert comm_data["document"]["id"] == f"doc_{task_id}_001"
    assert set(comm_data) == {"schema", "document", "sections", "datasets", "files", "warnings"}
    assert comm_data["files"] == {
        "content_md": "001_content.md",
        "datasets_dir": "001_datasets",
        "dataset_audit_csv": "001_datasets/_audit_cells.csv",
    }
    assert validate_projection_payload("community", comm_data).valid
    dataset = comm_data["datasets"][0]
    csv_rows = list(
        csv.DictReader(
            io.StringIO((written["datasets"] / "records.csv").read_text(encoding="utf-8-sig"))
        )
    )
    assert dataset["row_count"] == len(dataset["rows"]) == len(csv_rows) == 2
    assert [row["record_id"] for row in dataset["rows"]] == [row["record_id"] for row in csv_rows]
    assert dataset["rows"][0]["raw"]["field"] == "原值A"
    assert validate_community_artifacts(written["community"]) == []


def test_write_outputs_can_omit_cli_support_files(tmp_path: Path):
    result = ParseResult(status=ResultStatus.SUCCESS)
    result.entities = DocumentEntities(document_type="business_license")

    task_id, written = write_outputs(
        result,
        tmp_path,
        file_id="001",
        task_id="test_task_default_cli",
        include_mirror=False,
        include_manifest=False,
    )

    task_dir = tmp_path / task_id
    assert {"community", "content", "datasets"} <= set(written)
    assert "mirror" not in written
    assert not (task_dir / "001_mirror.json").exists()
    assert not (task_dir / "manifest.json").exists()


def test_content_markdown_is_identical_between_default_and_all_modes(tmp_path: Path):
    result = ParseResult(status=ResultStatus.SUCCESS)
    result.entities = DocumentEntities(document_type="business_license")

    _default_task, default_written = write_outputs(
        result,
        tmp_path,
        file_id="001",
        task_id="test_task_default_markdown",
        include_mirror=False,
        include_manifest=False,
    )
    _all_task, all_written = write_outputs(
        result,
        tmp_path,
        file_id="001",
        task_id="test_task_all_markdown",
        include_mirror=True,
        include_manifest=True,
    )

    assert default_written["content"].read_bytes() == all_written["content"].read_bytes()


def test_community_json_records_markdown_image_omission(tmp_path: Path):
    result = ParseResult(
        status=ResultStatus.SUCCESS,
        pages=[PageContent(page_number=1, texts=[TextBlock(content='<img src="imgs/missing.jpg" />')])],
        entities=DocumentEntities(document_type="id_card"),
    )

    _task_id, written = write_outputs(
        result,
        tmp_path,
        file_id="001",
        task_id="test_task_image_omission",
        include_mirror=False,
        include_manifest=False,
    )
    content = written["content"].read_text(encoding="utf-8")
    community = json.loads(written["community"].read_text(encoding="utf-8"))

    assert "<img" not in content
    assert any(warning["code"] == "MARKDOWN_IMAGE_OMITTED" for warning in community["warnings"])


def test_write_outputs_requires_overwrite_for_existing_run_id(tmp_path: Path):
    mirror = ParseResult(status=ResultStatus.SUCCESS)
    mirror.entities = DocumentEntities(document_type="business_license")

    write_outputs(
        mirror,
        tmp_path,
        file_id="001",
        task_id="test_task_overwrite",
    )

    with pytest.raises(FileExistsError):
        write_outputs(
            mirror,
            tmp_path,
            file_id="001",
            task_id="test_task_overwrite",
        )

    _task_id, written = write_outputs(
        mirror,
        tmp_path,
        file_id="001",
        task_id="test_task_overwrite",
        overwrite=True,
    )
    assert written["mirror"].is_file()


@pytest.mark.integration
def test_write_outputs_after_perceive(tmp_path: Path):
    if not LICENSE_FIXTURE.is_file():
        pytest.skip(f"missing fixture {LICENSE_FIXTURE}")

    result = asyncio.run(
        perceive_document(
            LICENSE_FIXTURE,
            PerceiveOptions(policy=normalize_parse_policy(enhance_mode="standard")),
        )
    )
    task_id, written = write_outputs(
        result,
        tmp_path,
        file_path=str(LICENSE_FIXTURE),
    )

    assert (tmp_path / task_id / "001_mirror.json").exists()
    mirror_json = json.loads((tmp_path / task_id / "001_mirror.json").read_text(encoding="utf-8"))
    assert mirror_json["source"]["provenance"]["output_ids"]["task_id"] == task_id
    assert mirror_json["document"]["document_id"] == f"doc_{task_id}_001"
    if "community" in written:
        comm_json = json.loads(written["community"].read_text(encoding="utf-8"))
        assert comm_json["document"]["id"] == f"doc_{task_id}_001"
        assert validate_projection_payload("community", comm_json).valid
