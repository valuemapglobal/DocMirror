# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0


def test_tnp_stage_modules_expose_symbols():
    from docmirror.core.table.pipeline import stage_domain, stage_header, stage_preamble, stage_structure
    from docmirror.core.table.postprocess import post_process_table

    assert callable(post_process_table)
    assert callable(stage_header.run)
    assert callable(stage_preamble._strip_preamble)
    assert callable(stage_preamble.run)
    assert callable(stage_structure.merge_split_rows)
    assert callable(stage_structure.run)
    assert callable(stage_domain.run_stages)
    assert callable(stage_domain.resolve_hook_names)


def test_tnp_staged_matches_monolith_on_sample():
    from docmirror.core.table.pipeline import TableNormalizeContext
    from docmirror.core.table.pipeline.stage_domain import run_stages
    from docmirror.core.table.postprocess import post_process_table
    from docmirror.configs.models.extraction_profile import ExtractionProfile

    rows = [
        ["交易单号", "交易时间", "金额(元)"],
        ["T001", "2024-01-01", "100.00"],
        ["T002", "2024-01-02", "200.00"],
    ]
    profile = ExtractionProfile(profile_id="borderless_ledger_wechat", use_tnp_staged=True)
    ctx = TableNormalizeContext(rows=rows, profile=profile, confirmed_header=rows[0])
    staged_rows, kv_staged = run_stages(ctx, rows)
    mono_rows, kv_mono = post_process_table(rows, confirmed_header=rows[0])
    assert staged_rows == mono_rows
    assert kv_staged == kv_mono


def test_tnp_hooks_package():
    from docmirror.core.table.pipeline.hooks import run_generic_hook, run_ledger_borderless_hook

    assert callable(run_generic_hook)
    assert callable(run_ledger_borderless_hook)
