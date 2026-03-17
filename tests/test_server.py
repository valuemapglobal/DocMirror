# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

import pytest
from fastapi.testclient import TestClient
from pathlib import Path

# Need to skip if fastapi is not installed
fastapi = pytest.importorskip("fastapi")

from docmirror.server.api import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.2.0"}

def test_parse_document_missing_file():
    response = client.post("/v1/parse")
    assert response.status_code == 422 # Validation error for missing form data

def test_parse_valid_document(tmp_path):
    # Create a dummy text file masking as a supported image/doc
    # Since DocMirror is robust, an empty or invalid doc will return a clean Failure API payload, not a 500 error.
    dummy_file = tmp_path / "test.txt"
    dummy_file.write_text("Hello DocMirror Server")
    
    with open(dummy_file, "rb") as f:
        # FastAPI TestClient upload
        response = client.post(
            "/v1/parse", 
            files={"file": ("test.txt", f, "text/plain")}
        )
        
    assert response.status_code in (200, 422)
    payload = response.json()
    assert "status" in payload
    assert "success" in payload
    assert "identity" in payload
    assert "blocks" in payload