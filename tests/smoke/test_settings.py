# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Settings configuration tests.
"""

import os

import pytest

from docmirror.configs.runtime.settings import DocMirrorSettings

pytestmark = [pytest.mark.tier_smoke]


class TestDocMirrorSettings:
    """Test DocMirrorSettings configuration."""

    def test_default_values(self):
        """Default settings should have sensible values."""
        settings = DocMirrorSettings()
        assert settings.default_enhance_mode == "standard"
        assert settings.max_pages == 200
        assert settings.ocr_dpi == 150
        assert settings.fail_strategy == "skip"

    def test_from_env_defaults(self):
        """from_env should use defaults when env vars not set."""
        settings = DocMirrorSettings.from_env()
        assert settings.default_enhance_mode == "standard"

    def test_from_env_override(self, monkeypatch):
        """from_env should respect DOCMIRROR_ env vars."""
        monkeypatch.setenv("DOCMIRROR_ENHANCE_MODE", "full")
        monkeypatch.setenv("DOCMIRROR_MAX_PAGES", "50")

        settings = DocMirrorSettings.from_env()
        assert settings.default_enhance_mode == "full"
        assert settings.max_pages == 50

    def test_to_dict(self):
        """to_dict should return orchestrator-compatible config."""
        settings = DocMirrorSettings()
        d = settings.to_dict()
        assert "enhance_mode" in d
        assert "EvidenceEngine" in d
        assert "Validator" in d
        assert d["MirrorCore"]["schema"] == "vnext"

    def test_mirror_core_settings_env_override(self, monkeypatch):
        """MirrorCore env vars should override YAML defaults except removed schemas."""
        monkeypatch.setenv("DOCMIRROR_MIRROR_SCHEMA", "unsupported_schema")
        monkeypatch.setenv("DOCMIRROR_MIRROR_CORE_PROFILE", "test_profile")
        monkeypatch.setenv("DOCMIRROR_MIRROR_CORE_ENGINE_VERSION", "9.9.9")

        settings = DocMirrorSettings.from_env()

        assert settings.mirror_core_schema == "vnext"
        assert settings.mirror_core_profile == "test_profile"
        assert settings.mirror_core_engine_version == "9.9.9"

    def test_model_paths_default_none(self):
        """Model paths should default to None."""
        settings = DocMirrorSettings()
        assert settings.layout_model_path is None
        assert settings.reading_order_model_path is None
        assert settings.formula_model_path is None

    def test_vlm_settings_available(self, monkeypatch):
        """VLM settings should be part of the runtime contract."""
        for key in (
            "DOCMIRROR_VLM_PROVIDER",
            "DOCMIRROR_VLM_MODEL",
            "DOCMIRROR_VLM_API_KEY",
            "DOCMIRROR_VLM_API_BASE",
            "DOCMIRROR_VLM_TIMEOUT",
            "DOCMIRROR_VLM_TEMPERATURE",
            "DOCMIRROR_VLM_MAX_TOKENS",
            "DOCMIRROR_VLM_PROMPT",
        ):
            monkeypatch.delenv(key, raising=False)

        settings = DocMirrorSettings.from_env()
        assert settings.vlm.provider == "openai"
        assert settings.vlm.model
        assert settings.vlm.api_key is None
        assert settings.vlm.timeout > 0
        assert "document analysis assistant" in settings.vlm.prompt

    def test_vlm_settings_env_override(self, monkeypatch):
        """VLM env vars should override YAML defaults."""
        monkeypatch.setenv("DOCMIRROR_VLM_PROVIDER", "dashscope")
        monkeypatch.setenv("DOCMIRROR_VLM_MODEL", "qwen-vl-max")
        monkeypatch.setenv("DOCMIRROR_VLM_API_KEY", "test-vlm-key")
        monkeypatch.setenv("DOCMIRROR_VLM_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        monkeypatch.setenv("DOCMIRROR_VLM_TIMEOUT", "12")

        settings = DocMirrorSettings.from_env()
        assert settings.vlm.provider == "dashscope"
        assert settings.vlm.model == "qwen-vl-max"
        assert settings.vlm.api_key == "test-vlm-key"
        assert settings.vlm.api_base == "https://dashscope.aliyuncs.com/compatible-mode/v1"
        assert settings.vlm.timeout == 12
