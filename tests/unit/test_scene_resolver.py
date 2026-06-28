# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for SceneResolver keyword matching."""

from docmirror.structure.scene.scene_resolver import resolve_document_scene


def test_scene_resolver_collapses_whitespace_for_cjk_keywords():
    broken = "对方户\n名\n借方发生额"
    result = resolve_document_scene(broken, min_confidence=0.70)
    assert result.scene == "bank_statement"
    assert result.confidence >= 0.70


def test_scene_resolver_ccb_account_detail_title():
    text = "中国建设银行账户明细信息\n打印日期：2023年12月26日"
    result = resolve_document_scene(text)
    assert result.scene == "bank_statement"
