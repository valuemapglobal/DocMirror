# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.tier_e2e, pytest.mark.integration]

# Need to skip if fastapi is not installed
fastapi = pytest.importorskip("fastapi")

from docmirror.server.api import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data

def test_parse_document_missing_file():
    response = client.post("/v1/parse")
    assert response.status_code == 422 # Validation error for missing form data

def test_parse_valid_document(tmp_path):
    # Create a dummy text file masking as a supported image/doc
    # Since DocMirror is robust, an empty or invalid doc will return a clean Failure API payload, not a 500 error.
    dummy_file = tmp_path / "test.txt"
    dummy_file.write_text("Hello DocMirror Server")

    with open(dummy_file, "rb") as f:
        response = client.post(
            "/v1/parse",
            files={"file": ("test.txt", f, "text/plain")}
        )

    assert response.status_code in (200, 422)
    payload = response.json()
    if response.status_code == 200:
        assert payload["status"] in {"success", "partial", "failed"}
        assert "task_id" in payload
        assert "inputs" in payload
        assert "artifacts" in payload
        assert "errors" in payload
        assert "mirror" not in payload
        assert "mirror" not in payload["artifacts"]

def test_parse_endpoint_has_no_delivery_selection_parameters():
    parameters = {
        parameter["name"]
        for parameter in client.get("/openapi.json").json()["paths"]["/v1/parse"]["post"].get("parameters", [])
    }
    assert not parameters & {"formats", "editions", "geometry", "include_geometry", "include_text", "mirror_level"}
