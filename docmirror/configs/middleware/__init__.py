# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Middleware Execution Platform (MEP) — catalog and pipeline resolver.

The MEP is DocMirror's middleware orchestration layer. It loads the middleware
catalog from ``middleware_catalog.yaml``, validates that enhancement profile
references resolve to importable ``BaseMiddleware`` subclasses, and resolves
ordered pipeline name lists for a given content model and enhance mode.

Public API::

    load_catalog() / MiddlewareSpec     Catalog SSOT with stage, depends_on, when guards
    get_middleware_class()              Dynamic import of middleware by catalog name
    validate_catalog()                  Cross-check catalog vs enhancement profiles
    resolve_pipeline()                  Content model × mode → filtered middleware list
    invalidate_middleware_cache()       Clear catalog and format caches
"""

from docmirror.configs.middleware.catalog import (
    MiddlewareSpec,
    get_middleware_class,
    get_middleware_stage,
    invalidate_middleware_cache,
    list_catalog_names,
    load_catalog,
    validate_catalog,
)
from docmirror.configs.middleware.resolver import resolve_pipeline

__all__ = [
    "MiddlewareSpec",
    "get_middleware_class",
    "get_middleware_stage",
    "invalidate_middleware_cache",
    "list_catalog_names",
    "load_catalog",
    "resolve_pipeline",
    "validate_catalog",
]
