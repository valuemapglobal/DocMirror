# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Mutation tracking models — data lineage for middleware audit trail.

Re-exports ``Mutation`` from ``tracking.mutation``. Every middleware operation
that transforms parse data should record a ``Mutation`` for 100% operation
traceability to meet audit requirements.
"""

from .mutation import Mutation

__all__ = ["Mutation"]
