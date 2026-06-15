# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Domain Plugin Interface
=======================

Extensible plugin system for domain-specific document processing.

Usage::

    from docmirror.plugins import registry

    registry.list_plugins()
    plugin = registry.get("bank_statement")
"""

from __future__ import annotations

from docmirror.plugins.plugin_registry import DomainPlugin, PluginRegistry, registry

_license_manager = None
_plugin_manager = None


def _get_license_manager():
    global _license_manager
    if _license_manager is None:
        from docmirror.plugins.licensing.online import license_manager as _lm

        _license_manager = _lm
    return _license_manager


def _get_plugin_manager():
    global _plugin_manager
    if _plugin_manager is None:
        from docmirror.plugins.manager import plugin_manager as _pm

        _plugin_manager = _pm
    return _plugin_manager


license_manager = _get_license_manager()
plugin_manager = _get_plugin_manager()

__all__ = [
    "DomainPlugin",
    "PluginRegistry",
    "registry",
    "license_manager",
    "plugin_manager",
]
