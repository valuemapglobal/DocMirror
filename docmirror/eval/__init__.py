# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Evaluation / TQG infrastructure (CPA design 12 — moved from core.evaluation)."""

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
