# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Evaluation oracles — non-production semantic and structural check helpers.

Hosts specialized oracle engines (e.g., semantic table understanding) that
score parse output against higher-level expectations. Not imported by the
runtime parse pipeline; intended for tests, TQG tracks, and research tooling.
"""
