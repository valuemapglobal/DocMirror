# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""Evaluation module for quality loop."""

from docmirror.core.evaluation.benchmark_runner import run_benchmark_matrix, save_benchmark_result
from docmirror.core.evaluation.golden_loader import GoldenCase, load_golden_matrix
from docmirror.core.evaluation.metrics import compute_metrics, evidence_fingerprint

__all__ = [
    "compute_metrics",
    "evidence_fingerprint",
    "GoldenCase",
    "load_golden_matrix",
    "run_benchmark_matrix",
    "save_benchmark_result",
]
