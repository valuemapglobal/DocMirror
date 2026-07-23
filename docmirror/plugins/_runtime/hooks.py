# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Plugin hook specifications using pluggy — GA1.0-EC-01 §Component 5.

This module defines the canonical hook interface that all DocMirror plugins
can implement. The ``docmirror_plugin_*`` entry points discovered by
:mod:`docmirror.plugins.discovery` register themselves against these hooks.

Usage::

    from docmirror.plugins.hooks import hookimpl

    class MyPlugin:
        @hookimpl
        def docmirror_plugin_manifest(self):
            return {
                "name": "my-plugin",
                "version": "0.1.0",
                "supported_types": ["bank_statement"],
            }

Design notes:
    - Hook specifications are additive. New hooks can be added in minor
      versions without breaking existing plugins.
    - Plugins return ``None`` to skip; return a value to apply changes.
    - The hook system is optional — bundled plugins in ``docmirror/plugins/``
      continue to use the existing ``PluginRegistry`` directly. The pluggy
      system is for **third-party** plugin packages distributed via PyPI.
"""

from __future__ import annotations

from typing import Any

import pluggy

# ── Hook specification markers ──

hookspec = pluggy.HookspecMarker("docmirror")
hookimpl = pluggy.HookimplMarker("docmirror")

# ── Project Name ──

PROJECT_NAME = "docmirror"


# ── Hook Specifications ──


@hookspec
def docmirror_plugin_provider() -> Any:
    """Return a :class:`docmirror.plugin_api.PluginProvider` runtime manifest.

    This is the only third-party registration hook. Pluggy is discovery
    transport; execution is owned exclusively by post-seal projectors.
    """


__all__ = [
    "hookspec",
    "hookimpl",
    "PROJECT_NAME",
    "docmirror_plugin_provider",
]
