# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
DocMirror configuration package.

Layout::

    configs/
      paths.py              # path constants
      yaml/                 # all declarative YAML
      runtime/              # settings, performance, yaml loader
      pipeline/             # middleware orchestration
      scene/                # scene keyword corpus loader
      domain/               # entity identity + key synonyms
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
from docmirror.configs.pipeline.registry import FORMAT_PIPELINES, get_pipeline_config
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
    "FORMAT_PIPELINES",
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
