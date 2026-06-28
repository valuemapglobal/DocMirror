# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Deprecated: This module has moved to ``docmirror.output.serialization``.
"""

import warnings  # noqa: E402
warnings.warn(
    "Importing from 'docmirror.models.serialization' is deprecated. "
    "Use 'docmirror.output.serialization' instead.",
    DeprecationWarning,
    stacklevel=2,
)
from docmirror.output.serialization import *  # noqa: F401,F403,E402

__all__ = [
    "json_default",
    "to_json_safe",
    "dumps_json",
    "assert_json_serializable",
]
