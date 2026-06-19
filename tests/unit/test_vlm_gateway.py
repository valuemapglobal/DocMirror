# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import numpy as np
import pytest
from unittest.mock import patch, MagicMock

from docmirror.configs.runtime.settings import default_settings
from docmirror.core.ocr.vlm_gateway import vlm_ocr_provider


@pytest.fixture
def dummy_image():
    return np.zeros((100, 200, 3), dtype=np.uint8)


def test_vlm_gateway_rejects_missing_key_and_base(dummy_image):
    default_settings.vlm.provider = "openai"
    default_settings.vlm.api_key = None
    default_settings.vlm.api_base = None

    # Should log warning and return None
    res = vlm_ocr_provider(dummy_image, page_idx=1)
    assert res is None


def test_vlm_gateway_dispatches_openai_api(dummy_image):
    default_settings.vlm.provider = "openai"
    default_settings.vlm.model = "gpt-4o"
    default_settings.vlm.api_key = "test-openai-key"
    default_settings.vlm.api_base = None
    default_settings.vlm.prompt = "Test Prompt"
    default_settings.vlm.temperature = 0.0

    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "OpenAI Success Response"}}]
        }
        mock_post.return_value = mock_response

        res = vlm_ocr_provider(dummy_image, page_idx=0)
        
        assert res is not None
        assert res["content_type"] == "general"
        assert res["lines"][0]["text"] == "OpenAI Success Response"
        assert res["page_h"] == 100
        assert res["page_w"] == 200
        
        # Verify request parameters
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://api.openai.com/v1/chat/completions"
        assert kwargs["headers"]["Authorization"] == "Bearer test-openai-key"
        payload = kwargs["json"]
        assert payload["model"] == "gpt-4o"
        assert payload["temperature"] == 0.0
        assert payload["messages"][0]["content"][0]["text"] == "Test Prompt"


def test_vlm_gateway_dispatches_gemini_api(dummy_image):
    default_settings.vlm.provider = "gemini"
    default_settings.vlm.model = "gemini-1.5-pro"
    default_settings.vlm.api_key = "test-gemini-key"
    default_settings.vlm.api_base = None
    default_settings.vlm.prompt = "Gemini Prompt"

    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Gemini Success Response"}]}}]
        }
        mock_post.return_value = mock_response

        res = vlm_ocr_provider(dummy_image, page_idx=1)
        
        assert res is not None
        assert res["lines"][0]["text"] == "Gemini Success Response"
        
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert "gemini-1.5-pro" in args[0]
        assert kwargs["params"]["key"] == "test-gemini-key"
        payload = kwargs["json"]
        assert payload["contents"][0]["parts"][0]["text"] == "Gemini Prompt"


def test_vlm_gateway_dispatches_anthropic_api(dummy_image):
    default_settings.vlm.provider = "anthropic"
    default_settings.vlm.model = "claude-3-5-sonnet-20240620"
    default_settings.vlm.api_key = "test-claude-key"
    default_settings.vlm.api_base = None
    default_settings.vlm.prompt = "Claude Prompt"

    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "content": [{"text": "Claude Success Response"}]
        }
        mock_post.return_value = mock_response

        res = vlm_ocr_provider(dummy_image, page_idx=2)
        
        assert res is not None
        assert res["lines"][0]["text"] == "Claude Success Response"
        
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://api.anthropic.com/v1/messages"
        assert kwargs["headers"]["x-api-key"] == "test-claude-key"
        payload = kwargs["json"]
        assert payload["model"] == "claude-3-5-sonnet-20240620"
        assert payload["messages"][0]["content"][1]["text"] == "Claude Prompt"


def test_vlm_gateway_custom_endpoint(dummy_image):
    default_settings.vlm.provider = "openai"
    default_settings.vlm.model = "gpt-4o"
    default_settings.vlm.api_key = "test-key"
    default_settings.vlm.api_base = "https://custom-gateway.local/v1/chat/completions"

    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Custom Endpoint Response"}}]
        }
        mock_post.value = mock_response
        mock_post.return_value = mock_response

        res = vlm_ocr_provider(dummy_image, page_idx=0)
        
        assert res is not None
        mock_post.assert_called_once()
        args, _ = mock_post.call_args
        assert args[0] == "https://custom-gateway.local/v1/chat/completions"


def test_vlm_gateway_custom_base_url_appending(dummy_image):
    default_settings.vlm.provider = "openai"
    default_settings.vlm.model = "qwen3.7-plus"
    default_settings.vlm.api_key = "test-key"
    default_settings.vlm.api_base = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Qwen Response"}}]
        }
        mock_post.return_value = mock_response

        res = vlm_ocr_provider(dummy_image, page_idx=0)
        
        assert res is not None
        mock_post.assert_called_once()
        args, _ = mock_post.call_args
        # Should automatically append /chat/completions
        assert args[0] == "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"


def test_vlm_gateway_dashscope_alias_uses_openai_compatible_api(dummy_image):
    default_settings.vlm.provider = "dashscope"
    default_settings.vlm.model = "qwen-vl-max"
    default_settings.vlm.api_key = "test-dashscope-key"
    default_settings.vlm.api_base = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "DashScope Alias Response"}}]
        }
        mock_post.return_value = mock_response

        res = vlm_ocr_provider(dummy_image, page_idx=0)

        assert res is not None
        assert res["lines"][0]["text"] == "DashScope Alias Response"
        args, kwargs = mock_post.call_args
        assert args[0] == "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        assert kwargs["headers"]["Authorization"] == "Bearer test-dashscope-key"


def test_vlm_gateway_azure_alias_accepts_custom_endpoint(dummy_image):
    default_settings.vlm.provider = "azure"
    default_settings.vlm.model = "deployment-name"
    default_settings.vlm.api_key = "test-azure-key"
    default_settings.vlm.api_base = "https://example.openai.azure.com/openai/deployments/deployment-name"

    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Azure Alias Response"}}]
        }
        mock_post.return_value = mock_response

        res = vlm_ocr_provider(dummy_image, page_idx=0)

        assert res is not None
        assert res["lines"][0]["text"] == "Azure Alias Response"
        args, kwargs = mock_post.call_args
        assert args[0] == "https://example.openai.azure.com/openai/deployments/deployment-name/chat/completions"
        assert kwargs["headers"]["Authorization"] == "Bearer test-azure-key"



def test_vlm_gateway_exceptions_caught_gracefully(dummy_image):
    default_settings.vlm.provider = "openai"
    default_settings.vlm.api_key = "test-key"

    with patch("requests.post", side_effect=Exception("API connection timeout")) as mock_post:
        # Should catch exception, log it, and return None gracefully (so pipeline can fallback)
        res = vlm_ocr_provider(dummy_image, page_idx=0)
        assert res is None
