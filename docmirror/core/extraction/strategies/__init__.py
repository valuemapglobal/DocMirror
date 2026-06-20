# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Extraction strategies package — pluggable document-structure extractors.

Purpose: Registry and implementations for alternative extraction strategies
(e.g. section-driven parsing) selected by document profile.

Main components: ``BaseExtractionStrategy``, ``SectionDrivenStrategy``,
``register_strategy``, ``get_strategy``.

Upstream: ``extraction.strategies.strategy_registry``, document profile.

Downstream: ``CoreExtractor`` when profile selects a non-default strategy.
"""
