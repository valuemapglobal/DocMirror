# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
DocMirror command-line interface package.

Re-exports Click command groups registered by ``docmirror.cli.main`` (parse,
classify, plugins, benchmark). End users invoke commands through the
``docmirror`` console script; this package holds subcommand implementations
only.
"""

from .plugins import plugins

__all__ = ["plugins"]
