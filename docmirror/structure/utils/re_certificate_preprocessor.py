# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
RE certificate preprocessor — domain-specific certificate image cleanup.

Purpose: Specialized preprocessing for real-estate certificate scans before
OCR (border trim, contrast boost).

Main components: Certificate-specific preprocess functions.

Upstream: Certificate document images.

Downstream: ``ocr`` recognition on certificate pages.
"""

try:
    from docmirror_enterprise.plugins.real_estate_certificate.preprocessors.image_preprocessor import (  # noqa: F401
        RealEstateCertificatePreprocessor,
    )
except ImportError:
    # Enterprise package not installed — preprocessor unavailable
    pass
