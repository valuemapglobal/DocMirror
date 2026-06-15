# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Transcoding adapter package — format normalization before extraction.

Re-exports ``transcode_session``, ``transcode_sync``, and
``FormatRequiresConverterError`` from the transcoding gate used by
``extraction_runner`` when FCR bindings require upstream conversion.
"""

from docmirror.adapters.transcode.gate import (
    FormatRequiresConverterError,
    transcode_session,
    transcode_sync,
)

__all__ = ["FormatRequiresConverterError", "transcode_session", "transcode_sync"]
