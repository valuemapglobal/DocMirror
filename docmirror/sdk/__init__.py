"""DocMirror Python SDK — typed, stable client for document parsing.

Provides ``DocMirrorClient`` (synchronous) and ``AsyncDocMirrorClient`` for
integrating DocMirror into Python applications without reading internal APIs.
"""

from docmirror.sdk.client import (
    DocMirrorClient,
    AsyncDocMirrorClient,
    DocMirrorError,
    parse_to_task,
)
from docmirror.sdk.integration.artifacts import ArtifactManifest, load_artifact_manifest, load_chunks_from_manifest
from docmirror.sdk.integration.errors import ErrorEnvelope, raise_on_error
from docmirror.sdk.integration.request import InputRef, ParseRequest

__all__ = [
    "DocMirrorClient",
    "AsyncDocMirrorClient",
    "DocMirrorError",
    "parse_to_task",
    "ArtifactManifest",
    "ErrorEnvelope",
    "InputRef",
    "ParseRequest",
    "load_artifact_manifest",
    "load_chunks_from_manifest",
    "raise_on_error",
]
