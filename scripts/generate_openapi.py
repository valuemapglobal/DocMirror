#!/usr/bin/env python3
"""Generate OpenAPI spec from the DocMirror FastAPI application.

Usage:
    python scripts/generate_openapi.py [--output docs/openapi/openapi.json]

The generated ``openapi.json`` is the single source of truth for all
auto-generated SDK clients (TypeScript, Go, Java).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def generate_openapi(output_path: str | None = None) -> dict:
    """Generate the OpenAPI 3.1 spec for the DocMirror REST API.

    Args:
        output_path: Optional path to write the spec JSON.

    Returns:
        The OpenAPI spec dict.
    """
    # Import the FastAPI app
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    os.environ.setdefault("DOCMIRROR_API_KEY", "")

    from docmirror.server.api import app

    openapi_spec = app.openapi()

    # Ensure standard OpenAPI fields
    openapi_spec.setdefault("openapi", "3.1.0")
    openapi_spec.setdefault("info", {})
    openapi_spec["info"].setdefault("title", "DocMirror Universal Parsing API")
    openapi_spec["info"].setdefault("version", app.version or "0.0.0")
    openapi_spec.setdefault(
        "servers",
        [
            {"url": "http://localhost:8000", "description": "Local development"},
            {"url": "https://api.docmirror.dev", "description": "Production"},
        ],
    )

    if output_path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(openapi_spec, indent=2, ensure_ascii=False, default=str))
        print(f"OpenAPI spec written to {output.resolve()}")

    return openapi_spec


if __name__ == "__main__":
    output = sys.argv[1] if len(sys.argv) > 1 else "docs/openapi/openapi.json"
    generate_openapi(output)
