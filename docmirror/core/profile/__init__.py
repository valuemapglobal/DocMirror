# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Profile package — extraction profile registry and layout profile resolution.

Purpose: Loads YAML/JSON extraction profiles and resolves layout profile IDs
from document signals.

Main components: ``load_profiles``, ``resolve_layout_profile``.

Upstream: Config files, ``scene.scene_resolver`` output.

Downstream: ``pipeline.document_profile``, ``extract.engine``.
"""

from docmirror.core.profile.registry import get_profile, match_layout_profile
from docmirror.core.profile.resolver import resolve_layout_profile

__all__ = ["get_profile", "match_layout_profile", "resolve_layout_profile"]
