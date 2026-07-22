# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path

from docmirror.server import mcp
from docmirror.server.task_result import TaskResult


class _Client:
    def parse(self, path: Path, *, mode: str):
        assert path.is_file()
        assert mode == "accurate"
        return TaskResult(
            task_id="task_mcp",
            status="success",
            artifacts={"community": "001_community.json", "mirror": "001_mirror.json"},
            edition_availability={"community": {"status": "written"}, "mirror": {"status": "written"}},
        )


def test_mcp_returns_public_task_result_instead_of_internal_payload(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "sample.pdf"
    source.write_bytes(b"PDF")
    monkeypatch.setattr(mcp, "_core", {"client": _Client()})

    payload = json.loads(mcp._parse_document_impl(str(source), "accurate"))

    assert payload["task_id"] == "task_mcp"
    assert payload["artifacts"] == {"community": "001_community.json"}
    assert "mirror" not in payload
    assert "mirror" not in payload["edition_availability"]
