# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
DocMirror core package — document processing engine public surface.

Purpose: Re-exports the primary extraction entry points (``CoreExtractor``,
``FitzEngine``, ``PreAnalyzer``) for callers that import from
``docmirror.core`` directly.

Main components: ``CoreExtractor``, ``FitzEngine``, ``PreAnalyzer``,
``PreAnalysisResult``.

Upstream: Application code and ``docmirror.core.entry`` factory.

Downstream: ``extraction``, ``analyze``, and the full parse pipeline.
"""

_EXPORTS = {
    "CoreExtractor": ("docmirror.core.extraction.extractor", "CoreExtractor"),
    "FitzEngine": ("docmirror.core.extraction.foundation", "FitzEngine"),
    "PreAnalysisResult": ("docmirror.core.analyze.pre_analyzer", "PreAnalysisResult"),
    "PreAnalyzer": ("docmirror.core.analyze.pre_analyzer", "PreAnalyzer"),
}


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attr_name = _EXPORTS[name]
    from importlib import import_module

    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value

__all__ = ["CoreExtractor", "FitzEngine", "PreAnalyzer", "PreAnalysisResult"]
