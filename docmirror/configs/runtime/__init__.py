# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Runtime deployment settings — yaml defaults + env overrides."""

from docmirror.configs.runtime.performance import (
    auto_page_concurrency,
    effective_page_workers,
    page_level_parallel_active,
    page_level_parallel_context,
    resolve_max_page_concurrency,
    resolve_max_process_workers,
    resolve_page_executor,
)
from docmirror.configs.runtime.settings import DocMirrorSettings, default_settings
from docmirror.configs.runtime.yaml_loader import YamlConfigLoader, config_loader, get_config

__all__ = [
    "DocMirrorSettings",
    "YamlConfigLoader",
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
]
