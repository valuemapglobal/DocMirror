# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Extract layers — backend registry for tiered table extraction.

Purpose: Package marker for physical extraction backends (PyMuPDF, RapidTable,
HTML parse) invoked by ``extract.engine``.

Main components: Backend callables from ``extract.layers.backends``.

Upstream: ``extract.engine`` tier dispatch.

Downstream: Raw table matrices to ``extract.best_candidate``.
"""

