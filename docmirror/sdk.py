"""DocMirror Python SDK — backward-compatible facade.

Re-exports the modern typed SDK client and integration types from their
canonical locations.  Existing ``from docmirror.sdk import parse_to_task``
imports continue to work.
"""

from __future__ import annotations

# Facade: re-export from canonical locations
from docmirror.sdk.client import (       # noqa: F401
    DocMirrorClient,
    AsyncDocMirrorClient,
    parse_to_task,
)
from docmirror.integration.request import ParseRequest, InputRef    # noqa: F401
from docmirror.integration.errors import (                          # noqa: F401
    ErrorEnvelope,
    DocMirrorError,
    raise_on_error,
)
from docmirror.integration.artifacts import (                       # noqa: F401
    ArtifactManifest,
    load_artifact_manifest,
    load_chunks_from_manifest,
)

__all__ = [
    "DocMirrorClient",
    "AsyncDocMirrorClient",
    "parse_to_task",
    "ParseRequest",
    "InputRef",
    "ErrorEnvelope",
    "DocMirrorError",
    "raise_on_error",
    "ArtifactManifest",
    "load_artifact_manifest",
    "load_chunks_from_manifest",
]
