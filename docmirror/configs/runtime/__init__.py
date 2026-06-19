# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Runtime configuration subpackage — YAML defaults with environment overrides.

Combines three concerns used at process startup and during extraction:

    settings        ``DocMirrorSettings`` dataclass (business limits, OCR params, logging)
    yaml_loader     ``YamlConfigLoader`` for ``docmirror.yaml`` with mtime-based reload
    performance     Page/process concurrency, executor backend, worker caps

Environment variables (``DOCMIRROR_*``) override YAML values where supported.
Import from here for a single entry point to runtime configuration.
"""

from docmirror.configs.runtime.performance import (
    DocumentWorkloadSignals,
    WorkerBudget,
    auto_page_concurrency,
    effective_page_workers,
    page_level_parallel_active,
    page_level_parallel_context,
    resolve_max_page_concurrency,
    resolve_max_process_workers,
    resolve_page_executor,
    resolve_semantic_worker_budget,
    resolve_worker_budget,
)
from docmirror.configs.runtime.settings import DocMirrorSettings, default_settings
from docmirror.configs.runtime.yaml_loader import YamlConfigLoader, config_loader, get_config

__all__ = [
    "DocMirrorSettings",
    "DocumentWorkloadSignals",
    "YamlConfigLoader",
    "WorkerBudget",
    "auto_page_concurrency",
    "config_loader",
    "default_settings",
    "effective_page_workers",
    "get_config",
    "page_level_parallel_active",
    "page_level_parallel_context",
    "resolve_max_page_concurrency",
    "resolve_max_process_workers",
    "resolve_page_executor",
    "resolve_semantic_worker_budget",
    "resolve_worker_budget",
]
