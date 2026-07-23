# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Generic community fallback domain package.

Re-exports the ``GenericCommunityPlugin`` singleton used when a document is classified
but is not one of the six premium community domains and generic fallback is enabled.

Pipeline role: generic Community projector registered in the shared Post-Seal
``PluginRegistry`` and selected only after ``SealedParseResult`` exists.

Key exports: ``GenericCommunityPlugin``, ``plugin``.
"""

from docmirror.plugins.generic.community_plugin import GenericCommunityPlugin, plugin

__all__ = ["GenericCommunityPlugin", "plugin"]
