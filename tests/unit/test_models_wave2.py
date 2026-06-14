# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Wave 2 tests: edition_serializer + table DEC path."""

from __future__ import annotations

from docmirror.models.edition_serializer import EditionContext, edition_serializer
from docmirror.models.entities.domain_result import DomainExtractionResult, DomainQuality, normalize_domain_result
from docmirror.models.schemas.loader import validate_dec
from docmirror.plugins._base.dec_builder import build_dec_kv
from docmirror.plugins._base.table_dec import build_table_dec, serialize_table_plugin_output
from docmirror.plugins.runner import _finalize_extract, _kv_community_payload
from docmirror.models.entities.parse_result import ParseResult


class _FakeTablePlugin:
    domain_name = "wechat_payment"
    display_name = "WeChat Payment"
    edition = "community"
    scene_keywords = ("微信支付",)

    @staticmethod
    def _detect_domain():
        return "cashflow_payment"


class TestEditionSerializer:
    def test_serialize_kv_dec(self):
        dec = normalize_domain_result(
            build_dec_kv("id_card", {"name": "张三", "id_number": "110101199001011234"})
        )
        ctx = EditionContext(
            edition="community",
            detected_type="id_card",
            document_name="test.pdf",
            archetype="key_value_document",
            domain="id_card",
            plugin_name="generic",
            plugin_display_name="Generic Community",
        )
        out = edition_serializer(dec, context=ctx)
        assert out["schema_version"] == "2.0"
        assert out["data"]["fields"]["name"] == "张三"
        assert out["document"]["document_type"] == "id_card"
        assert out["plugin"]["name"] == "generic"

    def test_serialize_table_dec(self):
        dec = build_table_dec(
            document_type="wechat_payment",
            identity_fields={"account_holder": {"normalized_value": "张三"}},
            records=[{"raw": {"amount": "1.00"}, "normalized": {"amount": 1.0}}],
            summary={"total_rows": 1, "total_income": 1.0, "total_expense": 0.0, "net_flow": 1.0},
        )
        ctx = EditionContext(
            edition="community",
            detected_type="wechat_payment",
            archetype="table_document",
            domain="cashflow_payment",
            plugin_name="wechat_payment",
            plugin_display_name="WeChat",
        )
        out = edition_serializer(dec, context=ctx)
        assert out["data"]["summary"]["total_rows"] == 1
        assert len(out["data"]["records"]) == 1

    def test_table_plugin_serialize_helper(self):
        pr = ParseResult()
        out = serialize_table_plugin_output(
            _FakeTablePlugin(),
            pr,
            identity_fields={},
            records=[{"raw": {}, "normalized": {}}],
            summary={"total_rows": 1},
        )
        assert out["schema_version"] == "2.0"
        assert out["document"]["archetype"] == "table_document"

    def test_v2_roundtrip_validate_payment(self):
        dec = build_table_dec(
            document_type="wechat_payment",
            identity_fields={},
            records=[{"raw": {}, "normalized": {}}],
            summary={"total_rows": 1},
        )
        ctx = EditionContext(
            detected_type="wechat_payment",
            archetype="table_document",
            domain="cashflow_payment",
            plugin_name="wechat_payment",
            plugin_display_name="WeChat",
        )
        v2 = edition_serializer(dec, context=ctx)
        roundtrip = normalize_domain_result(v2)
        assert roundtrip.document_type == "wechat_payment"
        assert len(roundtrip.structured_data["records"]) == 1
        issues = validate_dec(roundtrip)
        assert issues == []


class TestRunnerWave2:
    def test_finalize_serializes_dec_wrapper(self):
        pr = ParseResult()
        payload = build_dec_kv("bank_statement", {"account": "123"})
        out = _finalize_extract(pr, payload, edition="community", detected_type="bank_statement")
        assert out["schema_version"] == "2.0"
        assert out["data"]["fields"]["account"] == "123"

    def test_finalize_passes_through_v2(self):
        from tests.unit.test_models_wave1 import _sample_v2_payload

        pr = ParseResult()
        payload = _sample_v2_payload()
        out = _finalize_extract(pr, payload, edition="community", detected_type="alipay_payment")
        assert out is payload

    def test_kv_community_payload_uses_serializer(self):
        pr = ParseResult()

        class _GenericPlugin:
            domain_name = "generic"
            display_name = "Generic Community"
            edition = "community"
            scene_keywords = ()

        raw = build_dec_kv("id_card", {"name": "李四"})
        out = _kv_community_payload(pr, _GenericPlugin(), "id_card", raw)
        assert out["schema_version"] == "2.0"
        assert out["data"]["fields"]["name"] == "李四"
        assert out["plugin"]["name"] == "generic"
        assert out["document"]["document_type"] == "id_card"
