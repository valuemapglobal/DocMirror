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

__all__ = ["DocMirrorClient", "AsyncDocMirrorClient", "DocMirrorError", "parse_to_task"]
