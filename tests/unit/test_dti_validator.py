# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""DTI validator tests (design 09 Phase 2)."""

from __future__ import annotations

import pytest

from docmirror.configs.validators.dti import (
    load_business_scenes,
    validate_business_scene,
    validate_business_scenes,
)


class TestDtiValidator:
    def test_known_scene_valid(self):
        scenes = load_business_scenes()
        if not scenes:
            pytest.skip("scene_keywords.yaml not loaded")
        sample = next(iter(scenes))
        assert validate_business_scene(sample) is True

    def test_unknown_scene_invalid(self):
        scenes = load_business_scenes()
        if not scenes:
            pytest.skip("scene_keywords.yaml not loaded")
        assert validate_business_scene("__not_a_real_scene_xyz__") is False

    def test_generic_scenes_always_valid(self):
        assert validate_business_scene("") is True
        assert validate_business_scene("unknown") is True
        assert validate_business_scene("generic") is True

    def test_validate_business_scenes_returns_unknown(self):
        unknown = validate_business_scenes(["wechat_payment", "__fake_scene__"])
        if load_business_scenes():
            assert "__fake_scene__" in unknown

    def test_get_field_schema_bank_statement(self):
        from docmirror.models.entities.document_type import get_field_schema

        schema = get_field_schema("bank_statement")
        assert "account_number" in schema
