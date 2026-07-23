# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Document scene classification keyword corpus.

Re-exports the scene keyword loader API used by the EvidenceEngine, domain
plugins, and classification middleware. Keywords are supplied by plugin
resources and organized by ``business_scene`` (e.g.
``bank_statement``, ``invoice``).

Each scene spec contains ``include`` and ``exclude`` keyword lists used for
softmax priors, plugin ``scene_keywords`` tuples, and DTI validation.

Public API::

    get_scene_specs()           Raw per-scene include/exclude dicts
    get_scene_includes()        Include keywords (EvidenceEngine format)
    get_scene_excludes()        Exclude keywords per scene
    get_plugin_scene_keywords() Include-only tuples declared by providers
    compute_keyword_uniqueness()  Rarity weights across scenes
    invalidate_scene_cache()    Clear the merged resource cache
"""

from docmirror.configs.scene.loader import (
    compute_keyword_uniqueness,
    get_plugin_scene_keywords,
    get_scene_aliases,
    get_scene_excludes,
    get_scene_includes,
    get_scene_specs,
    invalidate_scene_cache,
)

__all__ = [
    "compute_keyword_uniqueness",
    "get_plugin_scene_keywords",
    "get_scene_aliases",
    "get_scene_excludes",
    "get_scene_includes",
    "get_scene_specs",
    "invalidate_scene_cache",
]
