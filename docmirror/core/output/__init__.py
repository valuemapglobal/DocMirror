# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Output package — export and visualization of extraction results.

Purpose: Converts ``BaseResult`` / ``ParseResult`` into Markdown, debug PDFs,
and other consumer formats.

Main components: ``markdown_exporter``, ``visualizer``.

Upstream: ``bridge.parse_result_bridge`` / ``CoreExtractor`` output.

Downstream: Benchmarks (OmniDocBench), debug workflows, file exports.
"""
