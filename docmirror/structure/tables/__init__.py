# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Table package — table normalization, merge, composition, and access layer.

Purpose: Post-extraction table processing: header detection, structure fix,
cross-page merge, logical/physical dual view, and consumer access API.

Main components: ``table.pipeline``, ``table.compose``, ``table.access``.

Upstream: ``extract.engine`` table blocks, OCR reconstruction.

Downstream: ``bridge.parse_result_bridge``, plugins via ``table.access``.
"""
