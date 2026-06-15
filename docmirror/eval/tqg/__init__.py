# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Test Quality Gate Platform (TQG) — unified manifest-driven evaluation (design 10).

Loads YAML gate manifests, executes cases through the parse pipeline, and
returns ``GateReport`` objects with pass/fail status and failure attribution.
Re-exports ``load_track_manifest``, ``load_all_manifests``, and ``run_tqg_case``
for CI integration.
"""

from docmirror.eval.tqg.manifest import load_track_manifest, load_all_manifests
from docmirror.eval.tqg.report import GateReport
from docmirror.eval.tqg.runner import run_tqg_case

__all__ = [
    "GateReport",
    "load_track_manifest",
    "load_all_manifests",
    "run_tqg_case",
]
