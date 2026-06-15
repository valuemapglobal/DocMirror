# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Deprecated re-export shim for compact merged bank ledger parsing.

Forwards all symbols from ``bank_statement.styles.compact_merged``. New code
should import from that module directly; this file exists for backward
compatibility and will be removed after two minor versions.

Pipeline role: none for new code — legacy import path only.

Dependencies: ``bank_statement.styles.compact_merged``.
"""

from docmirror.plugins.bank_statement.styles.compact_merged import *  # noqa: F403
