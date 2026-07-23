# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Central path constants for DocMirror configuration files.

All declarative configuration lives under ``configs/yaml/``. This module defines
``Path`` objects for every YAML file and subdirectory so loaders never hard-code
filesystem locations.

Key paths::

    DOCMIRROR_YAML              Root runtime config (business, OCR, performance, logging)
    FORMAT_CAPABILITIES_YAML    Format Capability Registry (FCR)
    ENHANCEMENT_PROFILES_YAML   Content-model × enhance-mode middleware profiles
    MIDDLEWARE_CATALOG_YAML     Middleware Execution Platform (MEP) catalog

Directory aliases (``CLASSIFICATION_DIR``, ``DOMAINS_DIR``, etc.) point at
``YAML_DIR`` after the flat-subdir layout was removed.
"""

from __future__ import annotations

from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent
YAML_DIR = CONFIG_DIR / "yaml"

# All declarative config lives under yaml/
DOCMIRROR_YAML = YAML_DIR / "docmirror.yaml"
OCR_CORRECTION_PACKS_DIR = YAML_DIR / "ocr_correction_packs"
FORMAT_CAPABILITIES_YAML = YAML_DIR / "format_capabilities.yaml"
ENHANCEMENT_PROFILES_YAML = YAML_DIR / "enhancement_profiles.yaml"
MIDDLEWARE_CATALOG_YAML = YAML_DIR / "middleware_catalog.yaml"
LICENSING_DIR = YAML_DIR / "licensing"
TIERS_YAML = LICENSING_DIR / "tiers.yaml"
LICENSE_FILE_SCHEMA = LICENSING_DIR / "license_file.schema.json"
MEP_GOLDEN_PROFILES_YAML = YAML_DIR / "golden" / "mep_profiles.yaml"
PIPELINE_WEIGHTS_YAML = YAML_DIR / "pipeline_weights.yaml"
GA_READINESS_YAML = YAML_DIR / "ga_readiness.yaml"
SUPPORT_MATRIX_YAML = YAML_DIR / "support_matrix.yaml"
GA_DEMO_MANIFEST_YAML = YAML_DIR / "ga_demo_manifest.yaml"
REAL_WORLD_FIXTURE_BANK_YAML = YAML_DIR / "test" / "real_world_fixture_bank.yaml"

# Directory aliases (flat subdirs removed)
CLASSIFICATION_DIR = YAML_DIR
DOMAINS_DIR = YAML_DIR
INSTITUTIONS_DIR = YAML_DIR
