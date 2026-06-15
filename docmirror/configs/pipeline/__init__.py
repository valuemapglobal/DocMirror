# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Middleware pipeline composition — backed by ``enhancement_profiles.yaml``.

Re-exports ``get_pipeline_config`` which is the primary entry point for callers
that know a file's transport type (``pdf``, ``docx``, …) or content model and
need the ordered middleware name list for extraction enhancement.
"""

from docmirror.configs.pipeline.registry import get_pipeline_config

__all__ = ["get_pipeline_config"]
