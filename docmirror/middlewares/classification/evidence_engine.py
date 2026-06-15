# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
120-type classification middleware shim (see ``middleware_catalog.yaml``).

Re-exports ``EvidenceEngine`` as the MEP-registered classification entry so
pipeline manifests reference a stable middleware module path while the core
implementation remains in ``docmirror.core.scene.evidence_engine``.
"""

from docmirror.core.scene.evidence_engine import EvidenceEngine

__all__ = ["EvidenceEngine"]
