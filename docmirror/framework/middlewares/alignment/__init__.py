# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Alignment middleware package — header alignment and amount splitting.

Re-exports column type inference, header/data alignment verification, split
debit/credit column detection, and the MEP ``HeaderAlignmentMiddleware`` wrapper.
"""

from .amount_splitter import detect_split_amount
from .header_alignment import infer_column_type, verify_header_data_alignment

__all__ = [
    "infer_column_type",
    "verify_header_data_alignment",
    "detect_split_amount",
]
