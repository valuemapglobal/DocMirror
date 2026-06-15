# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
DocMirror configuration package — declarative YAML loaders and runtime resolution.

This package is the single source of truth (SSOT) for all DocMirror configuration
that lives outside application code. It loads YAML files under ``configs/yaml/``,
exposes typed path constants, and provides resolver functions used by the
dispatcher, middleware pipeline, format router, and domain plugins.

Subpackages::

    paths.py              Path constants for every YAML file and config directory
    runtime/              ``docmirror.yaml`` loader, global settings, performance tuning
    format/               Format Capability Registry (FCR) — transport/content_model routing
    middleware/           Middleware Execution Platform (MEP) — catalog + pipeline resolver
    pipeline/             High-level middleware list composition for a file type
    scene/                Scene keyword corpus for document classification
    domain/               Entity identity fields and multilingual key synonym normalization
    models/               Layout and extraction profile Pydantic models (EPO)
    classification/       File-sort category rules and scene mapping
    validators/           Document Type Identity (DTI) validation helpers

Public API::

    Import path constants (``DOCMIRROR_YAML``, ``SCENE_KEYWORDS_YAML``, …),
    ``DocMirrorSettings``, ``get_config``, ``get_pipeline_config``,
    scene keyword accessors, and domain identity resolution from this module.
"""

from docmirror.configs.domain.registry import (
    DOMAIN_IDENTITY,
    KEY_SYNONYMS,
    normalize_entity_keys,
    resolve_identity,
)
from docmirror.configs.paths import (
    CLASSIFICATION_RULES_YAML,
    CONFIG_DIR,
    DOCMIRROR_YAML,
    INSTITUTION_REGISTRY_YAML,
    KEY_SYNONYMS_YAML,
    LAYOUT_PROFILES_YAML,
    SCENE_KEYWORDS_YAML,
    YAML_DIR,
)
from docmirror.configs.pipeline.registry import get_pipeline_config
from docmirror.configs.runtime.settings import DocMirrorSettings, default_settings
from docmirror.configs.runtime.yaml_loader import YamlConfigLoader, config_loader, get_config
from docmirror.configs.scene.loader import (
    compute_keyword_uniqueness,
    get_scene_includes,
    get_scene_specs,
    invalidate_scene_cache,
)

__all__ = [
    "CLASSIFICATION_RULES_YAML",
    "CONFIG_DIR",
    "DOCMIRROR_YAML",
    "DOMAIN_IDENTITY",
    "DocMirrorSettings",
    "INSTITUTION_REGISTRY_YAML",
    "KEY_SYNONYMS",
    "KEY_SYNONYMS_YAML",
    "LAYOUT_PROFILES_YAML",
    "SCENE_KEYWORDS_YAML",
    "YAML_DIR",
    "YamlConfigLoader",
    "config_loader",
    "default_settings",
    "get_config",
    "get_pipeline_config",
    "get_scene_includes",
    "get_scene_specs",
    "compute_keyword_uniqueness",
    "invalidate_scene_cache",
    "normalize_entity_keys",
    "resolve_identity",
]
