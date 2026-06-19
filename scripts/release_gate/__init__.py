# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Release gate package — pre-production quality orchestrator."""

from scripts.release_gate.runner import run_release_gate

__all__ = ["run_release_gate"]
