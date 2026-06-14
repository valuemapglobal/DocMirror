# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""Central paths for DocMirror configuration files."""

from __future__ import annotations

from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent
YAML_DIR = CONFIG_DIR / "yaml"

# All declarative config lives under yaml/
DOCMIRROR_YAML = YAML_DIR / "docmirror.yaml"
LAYOUT_PROFILES_YAML = YAML_DIR / "layout_profiles.yaml"
SCENE_KEYWORDS_YAML = YAML_DIR / "scene_keywords.yaml"
CLASSIFICATION_RULES_YAML = YAML_DIR / "classification_rules.yaml"
KEY_SYNONYMS_YAML = YAML_DIR / "key_synonyms.yaml"
INSTITUTION_REGISTRY_YAML = YAML_DIR / "institution_registry.yaml"
FORMAT_CAPABILITIES_YAML = YAML_DIR / "format_capabilities.yaml"
ENHANCEMENT_PROFILES_YAML = YAML_DIR / "enhancement_profiles.yaml"
MIDDLEWARE_CATALOG_YAML = YAML_DIR / "middleware_catalog.yaml"
PLUGIN_CAPABILITY_YAML = YAML_DIR / "plugin_capability.yaml"
LICENSING_DIR = YAML_DIR / "licensing"
TIERS_YAML = LICENSING_DIR / "tiers.yaml"
LICENSE_FILE_SCHEMA = LICENSING_DIR / "license_file.schema.json"
POST_EXTRACT_YAML = YAML_DIR / "post_extract.yaml"
MEP_GOLDEN_PROFILES_YAML = YAML_DIR / "golden" / "mep_profiles.yaml"

# Legacy aliases (flat subdirs removed)
CLASSIFICATION_DIR = YAML_DIR
DOMAINS_DIR = YAML_DIR
INSTITUTIONS_DIR = YAML_DIR
