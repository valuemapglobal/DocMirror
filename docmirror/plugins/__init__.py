# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Domain plugin package — public entry point for DocMirror's plugin system.

Re-exports the core registry types (``DomainPlugin``, ``PluginRegistry``,
``registry``) and lazily loads ``license_manager`` and ``plugin_manager`` so
importing ``docmirror.plugins`` does not pull in licensing or state I/O until
needed.

Pipeline role: after Mirror produces a ``ParseResult``, callers use
``runner.run_plugin_extract`` (not imported here) to match a domain plugin and
emit edition JSON; ``registry`` is the SSOT for registered plugins, while
``plugin_manager`` controls per-domain enable flags via ``state``.

Key exports: ``DomainPlugin``, ``PluginRegistry``, ``registry``,
``license_manager``, ``plugin_manager``.

Dependencies: ``plugin_registry`` (registry singleton), ``manager`` (enable/disable),
``licensing.online`` (lazy license manager).
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
