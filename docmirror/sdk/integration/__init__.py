"""DocMirror Developer Integration Contract (DIC).

Provides unified models for CLI, SDK, REST, Docker, RAG, and Agent
consumers: ParseRequest, ErrorEnvelope, ObservabilityContext, TaskResult,
and ArtifactManifest.

All integration points construct the same request shapes and consume the
same response / error / artifact contracts.  This module is the
single-source-of-truth for cross-surface integration, not a facade over
divergent internal representations.
"""

from docmirror.sdk.integration.request import InputRef, ParseRequest
from docmirror.sdk.integration.errors import ErrorEnvelope
from docmirror.sdk.integration.observability import ObservabilityContext, build_observability_context
from docmirror.sdk.integration.artifacts import ArtifactManifest, load_artifact_manifest, load_chunks_from_manifest

__all__ = [
    "InputRef",
    "ParseRequest",
    "ErrorEnvelope",
    "ObservabilityContext",
    "build_observability_context",
    "ArtifactManifest",
    "load_artifact_manifest",
    "load_chunks_from_manifest",
]
