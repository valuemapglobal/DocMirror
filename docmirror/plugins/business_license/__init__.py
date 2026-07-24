# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Business license community domain package.

Re-exports the registered ``BusinessLicensePlugin`` singleton for business
registration certificate documents.

Pipeline role: Community projector registered in the shared Post-Seal
``PluginRegistry``.

Key exports: ``BusinessLicensePlugin``, ``plugin``.
"""

from docmirror.plugins.business_license.community_plugin import BusinessLicensePlugin, plugin

__all__ = ["BusinessLicensePlugin", "plugin"]
