# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
DocMirror Dependency Injection Package
=======================================

Provides centralized dependency management for the DocMirror engine.

Usage::

    from docmirror.di import container, get_settings, get_dispatcher

    # Access services
    settings = get_settings()
    dispatcher = get_dispatcher()
"""

from docmirror.di.container import (
    DocMirrorContainer,
    container,
    get_cache,
    get_dispatcher,
    get_orchestrator,
    get_settings,
    reset_container,
)

__all__ = [
    "DocMirrorContainer",
    "container",
    "get_settings",
    "get_cache",
    "get_orchestrator",
    "get_dispatcher",
    "reset_container",
]
