from __future__ import annotations

import os
import unittest
from unittest.mock import patch, MagicMock

from src.analyzer.llm_provider import (
    MockProvider,
    get_provider_instance,
)
from src.analyzer.config import ProviderName


class TestMockProvider(unittest.TestCase):
    def test_mock_provider_returns_configured_response(self):
        from src.analyzer.llm_provider import MockProvider
        provider = MockProvider("test response")
        result = provider.complete("test prompt")
        
        self.assertEqual(result, "test response")
        self.assertEqual(provider.get_provider_name(), "mock")
        self.assertEqual(provider.get_model_name(), "mock-model")


class TestGetProviderInstance(unittest.TestCase):
    def test_returns_none_for_none_provider(self):
        result = get_provider_instance(ProviderName.NONE)
        self.assertIsNone(result)

    def test_returns_none_for_openai_without_credentials(self):
        result = get_provider_instance(ProviderName.OPENAI)
        self.assertIsNone(result)

    def test_creates_openai_provider_with_api_key(self):
        result = get_provider_instance(ProviderName.OPENAI, api_key="test-key")
        self.assertIsNotNone(result)
        self.assertEqual(result.get_provider_name(), "openai")

    def test_creates_anthropic_provider_with_api_key(self):
        result = get_provider_instance(ProviderName.ANTHROPIC, api_key="test-key")
        self.assertIsNotNone(result)
        self.assertEqual(result.get_provider_name(), "anthropic")

    def test_creates_google_provider_with_api_key(self):
        result = get_provider_instance(ProviderName.GOOGLE, api_key="test-key")
        self.assertIsNotNone(result)
        self.assertEqual(result.get_provider_name(), "google")

    def test_creates_azure_provider_with_credentials(self):
        import os
        with patch.dict(os.environ, {
            "AZURE_OPENAI_API_KEY": "test-key",
            "AZURE_OPENAI_ENDPOINT": "https://test.azure.com",
            "AZURE_OPENAI_DEPLOYMENT": "gpt-4"
        }):
            result = get_provider_instance(ProviderName.AZURE_OPENAI)
            self.assertIsNotNone(result)
            self.assertEqual(result.get_provider_name(), "azure_openai")


class TestProviderInitialization(unittest.TestCase):
    def test_provider_classes_require_api_key_validation(self):
        from src.analyzer.llm_provider import OpenAIProvider, AnthropicProvider
        
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises((ValueError, ModuleNotFoundError)):
                OpenAIProvider()
        
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises((ValueError, ModuleNotFoundError)):
                AnthropicProvider()


if __name__ == "__main__":
    unittest.main()