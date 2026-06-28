# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration: Mirror LTQG on bank grid fixture (CCB Zhenjiang Chaoqian)."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "bank_statement"
    / "建行-镇江超乾物流有限公司_1.pdf"
)


@pytest.mark.skipif(not FIXTURE.is_file(), reason="CCB fixture missing")
def test_ccb_mirror_ltqg_expected_rows():
    import asyncio

    from docmirror.structure.analysis.spe_consumer import mirror_expected_primary_rows
    from docmirror.input.entry.factory import PerceiveOptions, perceive_document

    result = asyncio.run(
        perceive_document(FIXTURE, options=PerceiveOptions(enhance_mode="standard"))
    )
    spe = result.parser_info.structure or result.to_mirror_json_vnext().get("meta", {}).get("structure") or {}
    assert int(spe.get("physical_table_count") or 0) >= 2
    assert spe.get("ltqg_enabled") is True
    assert int(spe.get("ltqg_expected_data_rows") or 0) >= 40
    assert int(spe.get("logical_table_count") or 0) == 1
    assert int(spe.get("ltqg_export_logical_tables") or spe.get("logical_table_count") or 0) == 1

    expected = mirror_expected_primary_rows(result)
    assert expected == int(spe.get("ltqg_expected_data_rows") or 0)

    ds = result.entities.domain_specific
    assert ds.get("mirror_expected_data_rows") == expected

    assert len(result.logical_tables) == 1
    assert all(lt.quality_passed for lt in result.logical_tables)

    api = result.to_mirror_json_vnext()
    assert api["meta"].get("quarantined_physical_count", 0) >= 2
    assert api["meta"].get("dual_view") is True
    assert api["meta"].get("mirror_expected_data_rows") == expected
    ltqg_meta = api["meta"].get("ltqg") or {}
    legacy = int(ltqg_meta.get("legacy_max_rows") or spe.get("ltqg_legacy_max_rows") or 0)
    if legacy:
        assert legacy > expected
