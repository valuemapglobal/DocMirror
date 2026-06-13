# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""DEC builder tests."""

from __future__ import annotations

from docmirror.plugins._base.dec_builder import build_dec_kv, dec_fields
from docmirror.plugins.id_card_community import plugin as id_card_plugin


class TestDecBuilder:
    def test_build_dec_kv_strips_empty(self):
        raw = build_dec_kv("id_card", {"name": "张三", "id_number": "", "gender": "男"})
        assert raw["document_type"] == "id_card"
        assert raw["entities"] == {"name": "张三", "gender": "男"}

    def test_dec_fields_from_dict(self):
        raw = build_dec_kv("id_card", {"name": "李四"})
        assert dec_fields(raw) == {"name": "李四"}

    def test_plugin_build_domain_data_returns_dec(self):
        raw = id_card_plugin.build_domain_data(
            {"Name": "王五"},
            {"id_number": "110101199001011234"},
        )
        assert raw is not None
        fields = dec_fields(raw)
        assert fields["name"] == "王五"
        assert fields["id_number"] == "110101199001011234"
