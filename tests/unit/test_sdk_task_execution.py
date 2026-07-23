# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ResultStatus
from docmirror.sdk import DocMirrorClient
from docmirror.sdk.integration.request import InputRef, ParseRequest


def _result() -> ParseResult:
    result = ParseResult(status=ResultStatus.SUCCESS)
    result.entities = DocumentEntities(document_type="business_license")
    return result


def test_parse_request_serializes_canonical_inputs() -> None:
    ref = InputRef(file_path="sample.pdf", file_name="sample.pdf")
    request = ParseRequest(inputs=[ref])

    assert request.inputs == [ref]
    assert request.to_dict()["inputs"][0]["file_name"] == "sample.pdf"
    assert set(request.to_dict()).isdisjoint({"input", "sync"})


def test_python_sdk_parse_many_uses_public_task_contract(tmp_path: Path, monkeypatch) -> None:
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.png"
    first.write_bytes(b"PDF")
    second.write_bytes(b"PNG")

    async def fake_perceive(_path, _options):
        return _result()

    monkeypatch.setattr("docmirror.server.task_executor.perceive_document", fake_perceive)
    client = DocMirrorClient(output_dir=tmp_path / "output")
    task = client.parse_many([first, second], workers=2)

    assert task.status == "success"
    assert [item["file_id"] for item in task.inputs] == ["001", "002"]
    assert "mirror" not in task.artifacts
    assert all("mirror" not in item["artifacts"] for item in task.inputs)
    assert first.is_file() and second.is_file()
