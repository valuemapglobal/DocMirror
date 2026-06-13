# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Backward-compatibility shim.

The real estate certificate image preprocessor has been migrated to the
enterprise plugin package:
    docmirror_enterprise.plugins.real_estate_certificate.preprocessors.image_preprocessor

This module re-exports all public symbols so that existing imports
continue to work when the enterprise package is installed.
"""

try:
    from docmirror_enterprise.plugins.real_estate_certificate.preprocessors.image_preprocessor import (  # noqa: F401
        RealEstateCertificatePreprocessor,
    )
except ImportError:
    # Enterprise package not installed — preprocessor unavailable
    pass
