# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
HTTP server package for DocMirror REST and shared output builders.

Contains the FastAPI application (``api``), Pydantic response schemas,
lightweight classification service, and edition-specific output builders used
by both the API and CLI. Recognition enriches the existing ``ParseResult``
zones, and edition projectors consume that ParseResult directly when assembling
outputs outside the server process.
"""
