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
def docmirror_plugin_manifest() -> dict[str, Any]:
    """Return plugin metadata.

    Returns:
        A dict with keys: ``name``, ``version``, ``domain``,
        ``display_name``, ``edition``, ``author``, ``description``,
        ``supported_types``.
        Return {} or None to indicate the plugin is not ready.
    """


@hookspec
def docmirror_augment_dmir(
    dmir: dict[str, Any],
    document_type: str,
) -> dict[str, Any] | None:
    """Augment DMIR with domain-specific data.

    Called after the initial DMIR is serialized from ParseResult.
    Plugins can add domain-specific fields, quality adjustments,
    or enrichment data.

    Args:
        dmir: The DMIR dict (to be mutated in-place or returned modified).
        document_type: The classified document type (e.g. "bank_statement").

    Returns:
        Augmented DMIR dict, or None to skip.
    """


@hookspec
def docmirror_classify_document(
    metadata: dict[str, Any],
    text_sample: str,
) -> str | None:
    """Classify a document type from metadata and text sample.

    Args:
        metadata: Document-level metadata (organization, subject, filename).
        text_sample: First 500 chars of the full text for classification.

    Returns:
        A document type string (e.g. "bank_statement"), or None to skip.
    """


@hookspec
def docmirror_validate_result(
    dmir: dict[str, Any],
) -> list[dict[str, Any]]:
    """Validate a parse result and return warnings.

    Args:
        dmir: The DMIR dict.

    Returns:
        List of warning dicts with ``field``, ``message``, ``severity`` keys,
        or empty list if validation passes.
    """


@hookspec(firstresult=True)
def docmirror_get_quality_gates(
    document_type: str,
) -> dict[str, float] | None:
    """Return quality gate thresholds for a document type.

    Args:
        document_type: The classified document type.

    Returns:
        Dict with metric->threshold mappings, or None to use defaults.
    """


__all__ = [
    "hookspec",
    "hookimpl",
    "PROJECT_NAME",
    "docmirror_plugin_manifest",
    "docmirror_augment_dmir",
    "docmirror_classify_document",
    "docmirror_validate_result",
    "docmirror_get_quality_gates",
]
