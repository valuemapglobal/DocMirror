# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Generic community fallback domain package.

Re-exports the ``GenericCommunityPlugin`` singleton used when a document is classified
but is not one of the six premium community domains and generic fallback is enabled.

Pipeline role: seventh community plugin slot; ``community.get_generic_community_plugin``
loads ``plugin`` for ``runner`` generic extract path.

Key exports: ``GenericCommunityPlugin``, ``plugin``.
"""

from docmirror.plugins.generic.community_plugin import GenericCommunityPlugin, plugin

__all__ = ["GenericCommunityPlugin", "plugin"]
