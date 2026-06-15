# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Construction and builder utilities — bridge legacy output to ``ParseResult``.

Re-exports ``ParseResultBridge`` which converts heterogeneous parser outputs
(legacy dicts, physical block lists, adapter-specific formats) into the unified
``ParseResult`` Mirror Object Contract.

See ``docmirror.core.bridge.parse_result_bridge`` for the canonical implementation
and design 09 §4.6 / Appendix C for the models-layer re-export rationale.
"""

from .parse_result_bridge import ParseResultBridge

__all__ = ["ParseResultBridge"]
