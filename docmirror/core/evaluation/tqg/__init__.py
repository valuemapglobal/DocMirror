# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Test Quality Gate Platform (TQG) — design 10."""

from docmirror.core.evaluation.tqg.manifest import load_track_manifest, load_all_manifests
from docmirror.core.evaluation.tqg.report import GateReport
from docmirror.core.evaluation.tqg.runner import run_tqg_case

__all__ = [
    "GateReport",
    "load_track_manifest",
    "load_all_manifests",
    "run_tqg_case",
]
