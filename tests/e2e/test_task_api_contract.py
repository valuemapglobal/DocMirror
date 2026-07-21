# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ResultStatus
from docmirror.server.api import app


def _mirror(document_type: str = "business_license") -> ParseResult:
    result = ParseResult(status=ResultStatus.SUCCESS)
    result.entities = DocumentEntities(
        document_type=document_type,
        domain_specific={
            "records": [
                {"record_id": "api:001", "normalized": {"value": "A"}, "raw": {"value": "原值A"}},
                {"record_id": "api:002", "normalized": {"value": "B"}, "raw": {"value": "原值B"}},
            ]
        },
    )
    return result


def test_task_api_wait_writes_artifacts(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DOCMIRROR_TASK_OUTPUT_DIR", str(tmp_path))

    async def fake_perceive(_path, _options):
        return _mirror()

    monkeypatch.setattr("docmirror.server.task_executor.perceive_document", fake_perceive)
    client = TestClient(app)
    response = client.post(
        "/v1/tasks?wait=true",
        files={"file": ("sample.pdf", b"PDF", "application/pdf")},
    )

    assert response.status_code == 200
    task = response.json()
    assert task["status"] == "success"
    task_id = task["task_id"]
    status = client.get(f"/v1/tasks/{task_id}").json()
    assert status["artifacts"]["mirror"] == "001_mirror.json"
    artifacts = client.get(f"/v1/tasks/{task_id}/artifacts").json()["artifacts"]
    assert artifacts["community"] == "001_community.json"
    community_response = client.get(f"/v1/tasks/{task_id}/artifacts/community")
    assert community_response.status_code == 200
    community = json.loads(community_response.content)
    dataset = community["datasets"][0]
    assert dataset["row_count"] == len(dataset["rows"]) == 2
    assert [row["record_id"] for row in dataset["rows"]] == ["api:001", "api:002"]
    assert dataset["rows"][0]["raw"]["value"] == "原值A"


def test_task_api_always_uses_fixed_delivery(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DOCMIRROR_TASK_OUTPUT_DIR", str(tmp_path))

    async def fake_perceive(_path, _options):
        return _mirror()

    monkeypatch.setattr("docmirror.server.task_executor.perceive_document", fake_perceive)
    client = TestClient(app)
    response = client.post(
        "/v1/tasks?wait=true",
        files={"file": ("sample.pdf", b"PDF", "application/pdf")},
    )

    assert response.status_code == 200
    task = response.json()
    assert task["status"] == "success"
    assert task["artifacts"]["community"] == "001_community.json"
    assert task["artifacts"]["mirror"] == "001_mirror.json"
    assert "editions" not in task
    assert "formats" not in task
    task_dir = tmp_path / task["task_id"]
    assert (task_dir / "001_mirror.json").exists()


def test_task_api_has_no_delivery_selection_parameters():
    schema = TestClient(app).get("/openapi.json").json()
    removed = {"formats", "editions", "geometry", "include_geometry", "include_text", "mirror_level"}
    for path in ("/v1/tasks", "/v1/tasks/batch"):
        parameters = {
            parameter["name"] for parameter in schema["paths"][path]["post"].get("parameters", [])
        }
        assert not parameters & removed


def test_batch_task_api_preserves_partial_failure(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DOCMIRROR_TASK_OUTPUT_DIR", str(tmp_path))

    async def fake_perceive(path, _options):
        if Path(path).read_text(encoding="utf-8") == "FAIL":
            raise ValueError("fixture failure")
        return _mirror("bank_statement")

    monkeypatch.setattr("docmirror.server.task_executor.perceive_document", fake_perceive)
    client = TestClient(app)
    response = client.post(
        "/v1/tasks/batch?wait=true",
        files=[
            ("files", ("ok.txt", b"OK", "text/plain")),
            ("files", ("fail.txt", b"FAIL", "text/plain")),
        ],
    )

    assert response.status_code == 200
    task = response.json()
    assert task["status"] == "partial"
    assert len(task["inputs"]) == 2
    assert len(task["errors"]) == 1
    assert any(key.startswith("001_") for key in task["artifacts"])


def test_task_api_accepts_background_work_and_persists_terminal_status(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DOCMIRROR_TASK_OUTPUT_DIR", str(tmp_path))

    async def fake_perceive(_path, _options):
        await asyncio.sleep(0.02)
        return _mirror()

    monkeypatch.setattr("docmirror.server.task_executor.perceive_document", fake_perceive)
    with TestClient(app) as client:
        response = client.post(
            "/v1/tasks",
            files={"file": ("sample.pdf", b"PDF", "application/pdf")},
        )
        assert response.status_code == 202
        task_id = response.json()["task_id"]

        deadline = time.monotonic() + 3.0
        status = client.get(f"/v1/tasks/{task_id}").json()
        while status["status"] == "running" and time.monotonic() < deadline:
            time.sleep(0.02)
            status = client.get(f"/v1/tasks/{task_id}").json()

        assert status["status"] == "success"
        assert status["progress"]["percent"] == 100.0
        assert status["artifacts"]["mirror"] == "001_mirror.json"
        assert client.get(f"/v1/tasks/{task_id}/artifacts/not_declared").status_code == 404


def test_task_api_unknown_task_is_not_found(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DOCMIRROR_TASK_OUTPUT_DIR", str(tmp_path))
    client = TestClient(app)

    assert client.get("/v1/tasks/task_missing").status_code == 404
    assert client.get("/v1/tasks/../outside").status_code == 404
