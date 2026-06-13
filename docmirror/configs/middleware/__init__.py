# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Middleware Execution Platform (MEP) — catalog and pipeline resolver."""

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
