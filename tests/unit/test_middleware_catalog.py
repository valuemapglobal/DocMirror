# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for MEP middleware catalog."""

from __future__ import annotations

import pytest

from docmirror.configs.middleware.catalog import (
    get_middleware_class,
    list_catalog_names,
    load_catalog,
    validate_catalog,
)
from docmirror.framework.middlewares.base import BaseMiddleware


def test_catalog_loads_all_production_middlewares():
    catalog = load_catalog()
    assert len(catalog) >= 10
    expected = {
        "LanguageDetector",
        "HeaderInferrer",
        "HeaderAlignment",
        "EntityExtractor",
        "GenericEntityExtractor",
        "EvidenceEngine",
        "InstitutionDetector",
        "Validator",
        "AnomalyDetector",
        # "SLMEntityExtractor",  # removed in v1.1
    }
    assert expected <= set(catalog.keys())


@pytest.mark.parametrize("name", list_catalog_names())
def test_catalog_imports_middleware_class(name: str):
    cls = get_middleware_class(name)
    assert issubclass(cls, BaseMiddleware)


def test_validate_catalog_ok():
    errors = validate_catalog()
    assert errors == []


def test_domain_plugin_bridge_not_in_catalog():
    catalog = load_catalog()
    assert "DomainPluginBridge" not in catalog
