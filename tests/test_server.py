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
    # Standard envelope
    assert "code" in payload
    assert "message" in payload
    assert "api_version" in payload
    assert "request_id" in payload
    assert "timestamp" in payload
    assert "data" in payload or "error" in payload
    assert "meta" in payload
    # meta should NOT contain request_id/timestamp (only at top level)
    assert "request_id" not in payload["meta"]
    assert "timestamp" not in payload["meta"]

def test_parse_with_include_text(tmp_path):
    """Verify include_text=true adds text and text_format to document."""
    dummy_file = tmp_path / "test.txt"
    dummy_file.write_text("Hello DocMirror include_text test")
    
    with open(dummy_file, "rb") as f:
        response = client.post(
            "/v1/parse?include_text=true",
            files={"file": ("test.txt", f, "text/plain")}
        )
    
    assert response.status_code in (200, 422)
    payload = response.json()
    assert "code" in payload
    
    if payload["code"] == 200:
        doc = payload["data"]["document"]
        assert "text" in doc
        assert doc["text_format"] == "markdown"

def test_parse_without_include_text(tmp_path):
    """Verify include_text=false (default) omits text from document."""
    dummy_file = tmp_path / "test.txt"
    dummy_file.write_text("Hello DocMirror no text test")
    
    with open(dummy_file, "rb") as f:
        response = client.post(
            "/v1/parse",
            files={"file": ("test.txt", f, "text/plain")}
        )
    
    assert response.status_code in (200, 422)
    payload = response.json()
    
    if payload["code"] == 200:
        doc = payload["data"]["document"]
        assert "text" not in doc