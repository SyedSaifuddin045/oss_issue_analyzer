from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from src.analyzer.config import ProviderName
from src.analyzer.llm_provider import (
    LLMRequest,
    LLMResponse,
    MockProvider,
    OpenAIProvider,
    get_provider_instance,
)


class TestMockProvider(unittest.TestCase):
    def test_mock_provider_returns_configured_response(self):
        provider = MockProvider("test response")
        result = provider.complete(
            LLMRequest(system="sys", user="test prompt", temperature=0.0, max_tokens=16)
        )

        self.assertEqual(result.content, "test response")
        self.assertEqual(provider.get_provider_name(), "mock")
        self.assertEqual(provider.get_model_name(), "mock-model")


class TestOpenAIProviderRequest(unittest.TestCase):
    def test_complete_uses_system_user_and_json_mode(self):
        provider = OpenAIProvider.__new__(OpenAIProvider)
        provider.model = "gpt-test"
        provider.client = MagicMock()

        response = MagicMock()
        response.choices = [MagicMock(message=MagicMock(content='{"difficulty":"easy","confidence":0.8,"core_problem":"x","strategic_guidance":["a","b","c","d"],"suggested_approach":["1","2","3"],"positive_signals":[],"warning_signals":[],"is_good_first_issue":true,"files_to_focus":[],"why_these_files":[],"uncertainty_notes":[]}'))]
        response.usage = MagicMock(total_tokens=123)
        provider.client.chat.completions.create.return_value = response

        result = provider.complete(
            LLMRequest(
                system="SYSTEM",
                user="USER",
                temperature=0.2,
                max_tokens=321,
                response_format={"type": "json_object"},
            )
        )

        self.assertEqual(result.model, "gpt-test")
        self.assertEqual(result.tokens_used, 123)
        provider.client.chat.completions.create.assert_called_once()
        kwargs = provider.client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs["messages"][0]["role"], "system")
        self.assertEqual(kwargs["messages"][0]["content"], "SYSTEM")
        self.assertEqual(kwargs["messages"][1]["content"], "USER")
        self.assertEqual(kwargs["response_format"], {"type": "json_object"})


class TestGetProviderInstance(unittest.TestCase):
    def test_returns_none_for_none_provider(self):
        self.assertIsNone(get_provider_instance(ProviderName.NONE))

    def test_returns_none_for_openai_without_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(get_provider_instance(ProviderName.OPENAI))

    def test_creates_openai_provider_with_api_key(self):
        result = get_provider_instance(ProviderName.OPENAI, api_key="test-key")
        self.assertIsNotNone(result)
        self.assertEqual(result.get_provider_name(), "openai")

    def test_creates_google_provider_with_api_key(self):
        result = get_provider_instance(ProviderName.GOOGLE, api_key="test-key")
        self.assertIsNotNone(result)
        self.assertEqual(result.get_provider_name(), "google")


class TestProviderInitialization(unittest.TestCase):
    def test_provider_classes_require_api_key_validation(self):
        from src.analyzer.llm_provider import AnthropicProvider

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises((ValueError, ModuleNotFoundError)):
                OpenAIProvider()

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises((ValueError, ModuleNotFoundError)):
                AnthropicProvider()


if __name__ == "__main__":
    unittest.main()
