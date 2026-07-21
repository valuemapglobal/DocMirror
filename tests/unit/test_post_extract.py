# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Post-extract hook catalog tests."""

from __future__ import annotations

from docmirror.plugins._runtime.post_extract.catalog import load_post_extract_catalog, resolve_post_extract_hooks


def test_post_extract_catalog_loads():
    catalog = load_post_extract_catalog()
    assert "edition_table_rebuild" in catalog
    assert "community_precision" in catalog
    assert "plugin_trust_projection" in catalog


def test_community_precision_runs_before_business_projection():
    hooks = resolve_post_extract_hooks(
        document_type="vat_invoice",
        edition="community",
        extracted={"plugin": {"name": "vat_invoice"}, "data": {}},
    )
    ids = [hook.hook_id for hook in hooks]
    assert ids.index("community_precision") < ids.index("community_business_projection")


def test_resolve_bank_statement_hooks():
    hooks = resolve_post_extract_hooks(
        document_type="bank_statement",
        edition="enterprise",
        extracted={"structured_data": {"transactions": []}},
    )
    ids = {h.hook_id for h in hooks}
    assert "edition_table_rebuild" in ids
