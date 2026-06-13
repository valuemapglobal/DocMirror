# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Middleware pipeline composition per file format."""

from docmirror.configs.pipeline.registry import FORMAT_PIPELINES, get_pipeline_config

__all__ = ["FORMAT_PIPELINES", "get_pipeline_config"]
