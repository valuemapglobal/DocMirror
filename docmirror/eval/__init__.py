# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Evaluation and Test Quality Gate (TQG) infrastructure (CPA design 12).

Provides golden-matrix loading, parse-quality metrics, benchmark runners, and
gate profiles used by CI and local regression checks. Public helpers include
``load_golden_matrix``, ``compute_metrics``, and ``run_benchmark_matrix``;
full TQG manifest execution lives under ``docmirror.eval.tqg``.
"""

from docmirror.eval.benchmark_runner import run_benchmark_matrix, save_benchmark_result
from docmirror.eval.golden_loader import GoldenCase, load_golden_matrix
from docmirror.eval.metrics import compute_metrics, evidence_fingerprint

__all__ = [
    "GoldenCase",
    "compute_metrics",
    "evidence_fingerprint",
    "load_golden_matrix",
    "run_benchmark_matrix",
    "save_benchmark_result",
]
