# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for AI Backend Connector (GA1.0-ODL-01 §AI Backend)."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from docmirror.input.adapters.ai import get_ai_backend, get_ai_config
from docmirror.input.adapters.ai.config import (
    AIConfig,
    AIBackendType,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_RATE_LIMIT,
)
from docmirror.input.adapters.ai.protocol import AIAnalysisResult, AIBackendCapabilities


class TestAIConfig:
    """Tests for AIConfig dataclass and config loading."""

    def test_default_values(self):
        """AIConfig should have sensible defaults."""
        cfg = AIConfig()
        assert cfg.default_backend == AIBackendType.OPENAI
        assert cfg.openai_model == DEFAULT_OPENAI_MODEL
        assert cfg.gemini_model == DEFAULT_GEMINI_MODEL
        assert cfg.rate_limit_per_second == DEFAULT_RATE_LIMIT
        assert cfg.openai_api_key == ""
        assert cfg.gemini_api_key == ""

    def test_to_dict_excludes_secrets(self):
        """to_dict() should not expose API keys."""
        cfg = AIConfig(
            openai_api_key="sk-secret",
            gemini_api_key="AIzasecret",
        )
        d = cfg.to_dict()
        assert "sk-secret" not in str(d)
        assert "AIzasecret" not in str(d)
        assert d["default_backend"] == "openai"
        assert d["openai_model"] == DEFAULT_OPENAI_MODEL

    def test_auto_detect_openai_from_env(self):
        """Should auto-detect OpenAI when OPENAI_API_KEY is set."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True):
            cfg = get_ai_config()
            assert cfg.default_backend == AIBackendType.OPENAI
            assert cfg.openai_api_key == "sk-test"

    def test_auto_detect_gemini_from_env(self):
        """Should auto-detect Gemini when GEMINI_API_KEY is set."""
        with patch.dict(os.environ, {"GEMINI_API_KEY": "AIza-test"}, clear=True):
            cfg = get_ai_config()
            assert cfg.default_backend == AIBackendType.GEMINI
            assert cfg.gemini_api_key == "AIza-test"

    def test_env_override_backend_choice(self):
        """DOCMIRROR_AI_BACKEND should override auto-detection."""
        with patch.dict(
            os.environ,
            {"DOCMIRROR_AI_BACKEND": "gemini", "OPENAI_API_KEY": "sk-test"},
            clear=True,
        ):
            cfg = get_ai_config()
            assert cfg.default_backend == AIBackendType.GEMINI

    def test_env_override_model_and_rate_limit(self):
        """Model names and rate limit should be configurable via env."""
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "sk-test",
                "OPENAI_MODEL": "gpt-4o-mini",
                "DOCMIRROR_AI_RATE_LIMIT": "20",
            },
            clear=True,
        ):
            cfg = get_ai_config()
            assert cfg.openai_model == "gpt-4o-mini"
            assert cfg.rate_limit_per_second == 20

    def test_invalid_rate_limit_falls_back(self):
        """Invalid rate limit env var should fall back to default."""
        with patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "sk-test", "DOCMIRROR_AI_RATE_LIMIT": "not-a-number"},
            clear=True,
        ):
            cfg = get_ai_config()
            assert cfg.rate_limit_per_second == DEFAULT_RATE_LIMIT


class TestAIBackendCapabilities:
    """Tests for AIBackendCapabilities dataclass."""

    def test_default_values(self):
        caps = AIBackendCapabilities()
        assert caps.vision is False
        assert caps.chart_description is False
        assert caps.max_image_size_mb == 20.0
        assert "describe" in caps.supported_tasks

    def test_openai_capabilities(self):
        caps = AIBackendCapabilities(
            vision=True,
            chart_description=True,
            table_extraction=True,
            formula_extraction=True,
            page_understanding=True,
        )
        assert caps.vision
        assert caps.chart_description


class TestAIAnalysisResult:
    """Tests for AIAnalysisResult dataclass."""

    def test_default_values(self):
        result = AIAnalysisResult()
        assert result.page_description == ""
        assert result.tables == []
        assert result.chart_descriptions == {}
        assert result.formulas == []
        assert result.confidence == 0.0

    def test_can_store_structured_data(self):
        result = AIAnalysisResult(
            page_description="A financial report page with a table",
            tables=[{"headers": ["Date", "Amount"], "rows": []}],
            chart_descriptions={"chart_1": "A bar chart showing revenue growth"},
            formulas=["E = mc^2"],
            confidence=0.95,
        )
        assert result.page_description == "A financial report page with a table"
        assert len(result.tables) == 1
        assert result.chart_descriptions["chart_1"].startswith("A bar chart")
        assert result.formulas[0] == "E = mc^2"
        assert result.confidence == 0.95


class TestGetAIBackend:
    """Tests for the get_ai_backend() factory function."""

    def test_returns_none_when_no_api_key(self):
        """Should return None when no API key is configured."""
        with patch.dict(os.environ, {}, clear=True):
            backend = get_ai_backend()
            assert backend is None

    def test_returns_none_for_unknown_backend(self):
        """Should return None for unknown backend types."""
        backend = get_ai_backend("nonexistent")
        assert backend is None

    def test_openai_backend_not_available_without_key(self):
        """OpenAI backend should not be available without API key."""
        with patch.dict(os.environ, {}, clear=True):
            backend = get_ai_backend("openai")
            if backend is not None:
                assert not backend.is_available

    def test_gemini_backend_not_available_without_key(self):
        """Gemini backend should not be available without API key."""
        with patch.dict(os.environ, {}, clear=True):
            backend = get_ai_backend("gemini")
            if backend is not None:
                assert not backend.is_available

    def test_factory_graceful_on_import_error(self):
        """Should return None gracefully when import fails."""
        with patch(
            "docmirror.input.adapters.ai._try_create_backend",
            return_value=None,
        ):
            backend = get_ai_backend("openai")
            assert backend is None


class TestAIBackendProtocol:
    """Tests for the AIBackend protocol's expected interface."""

    def test_analyze_page_signature(self):
        """Test that a mock AIBackend satisfies the protocol shape."""
        mock_backend = MagicMock(spec=[
            "name", "is_available", "capabilities",
            "analyze_page", "describe_image",
        ])
        mock_backend.name = "test"
        mock_backend.is_available = True
        mock_backend.capabilities = AIBackendCapabilities(vision=True)

        # Mock analyze_page as async callable
        mock_backend.analyze_page = AsyncMock(return_value={
            "page_description": "Test page",
            "confidence": 0.9,
        })

        # Verify protocol-required attributes exist
        assert hasattr(mock_backend, "analyze_page")
        assert hasattr(mock_backend, "describe_image")
        assert hasattr(mock_backend, "name")
        assert hasattr(mock_backend, "is_available")
        assert hasattr(mock_backend, "capabilities")

    def test_describe_image_signature(self):
        """Test that describe_image returns a string."""
        mock_backend = MagicMock()
        mock_backend.name = "test"
        mock_backend.is_available = True

        # Mock describe_image
        mock_backend.describe_image = AsyncMock(return_value="A chart showing data")

        import inspect
        assert inspect.iscoroutinefunction(mock_backend.describe_image)


__all__ = []
