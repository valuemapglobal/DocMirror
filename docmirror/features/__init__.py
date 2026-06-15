# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Optional product-feature layer built on EFPA parse outputs.

Hosts higher-level capabilities that consume ``ParseResult`` without modifying
the core parse pipeline: agent routing hints (L11), structure-aware RAG
chunking (L10), and multi-file package manifest plus cross-file consistency
checks (L20). Features are opt-in and safe to omit in minimal deployments.
"""

__all__: list[str] = []
