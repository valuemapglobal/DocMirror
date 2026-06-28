# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
DocMirror Dependency Injection Package
=======================================

Provides the process-wide service container for framework singletons.

Primary parsing API remains ``docmirror.input.pipeline.perceive_document()``.
Use this package when tests or extensions need shared ``ParserDispatcher`` /
``Orchestrator`` instances.

Usage::

    from docmirror.framework.di import get_dispatcher, get_orchestrator, reset_container

    dispatcher = get_dispatcher()
    orchestrator = get_orchestrator()
"""

from docmirror.framework.di.container import (
    DocMirrorContainer,
    container,
    get_dispatcher,
    get_orchestrator,
    get_settings,
    reset_container,
)

__all__ = [
    "DocMirrorContainer",
    "container",
    "get_settings",
    "get_dispatcher",
    "get_orchestrator",
    "reset_container",
]
