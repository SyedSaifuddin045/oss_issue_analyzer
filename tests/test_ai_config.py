from __future__ import annotations

import os
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

from src.analyzer.config import (
    AIConfig,
    ProviderName,
    ProviderCredentials,
    get_ai_config,
    get_credentials,
    save_provider_config,
    clear_provider_config,
    get_available_providers,
    CONFIG_DIR,
    CONFIG_FILE,
)


class TestConfigLoading(unittest.TestCase):
    def setUp(self):
        if CONFIG_FILE.exists():
            CONFIG_FILE.unlink()

    def tearDown(self):
        if CONFIG_FILE.exists():
            CONFIG_FILE.unlink()

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key-123"})
    def test_get_credentials_loads_from_env(self):
        creds = get_credentials()
        self.assertEqual(creds.openai_api_key, "test-key-123")

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "ant-test-key"})
    def test_get_credentials_anthropic(self):
        creds = get_credentials()
        self.assertEqual(creds.anthropic_api_key, "ant-test-key")

    @patch.dict(os.environ, {"GOOGLE_API_KEY": "google-test-key"})
    def test_get_credentials_google(self):
        creds = get_credentials()
        self.assertEqual(creds.google_api_key, "google-test-key")

    @patch.dict(os.environ, {
        "AZURE_OPENAI_API_KEY": "azure-key",
        "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com"
    })
    def test_get_credentials_azure(self):
        creds = get_credentials()
        self.assertEqual(creds.azure_openai_api_key, "azure-key")
        self.assertEqual(creds.azure_openai_endpoint, "https://test.openai.azure.com")

    @patch.dict(os.environ, {"AI_ENABLED": "false"})
    def test_ai_disabled_via_env(self):
        config = get_ai_config()
        self.assertFalse(config.enabled)

    @patch.dict(os.environ, {"AI_TIMEOUT_SECONDS": "60"})
    def test_custom_timeout(self):
        config = get_ai_config()
        self.assertEqual(config.timeout_seconds, 60)


class TestProviderSelection(unittest.TestCase):
    def setUp(self):
        if CONFIG_FILE.exists():
            CONFIG_FILE.unlink()

    def tearDown(self):
        if CONFIG_FILE.exists():
            CONFIG_FILE.unlink()

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_auto_detect_openai_provider(self):
        config = get_ai_config()
        self.assertEqual(config.provider, ProviderName.OPENAI)

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_auto_detect_anthropic_provider(self):
        config = get_ai_config()
        self.assertEqual(config.provider, ProviderName.ANTHROPIC)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key", "GOOGLE_API_KEY": "test-key"})
    def test_preference_order_openai_over_google(self):
        config = get_ai_config()
        self.assertEqual(config.provider, ProviderName.OPENAI)

    @patch.dict(os.environ, {}, clear=True)
    def test_no_provider_when_no_keys(self):
        config = get_ai_config()
        self.assertEqual(config.provider, ProviderName.NONE)

    def test_is_configured_returns_false_when_disabled(self):
        config = AIConfig(enabled=False, provider=ProviderName.OPENAI)
        self.assertFalse(config.is_configured)

    def test_is_configured_returns_false_when_no_provider(self):
        config = AIConfig(enabled=True, provider=ProviderName.NONE)
        self.assertFalse(config.is_configured)

    def test_is_configured_returns_true_when_configured(self):
        config = AIConfig(enabled=True, provider=ProviderName.OPENAI)
        self.assertTrue(config.is_configured)


class TestSaveProviderConfig(unittest.TestCase):
    def setUp(self):
        if CONFIG_FILE.exists():
            CONFIG_FILE.unlink()

    def tearDown(self):
        if CONFIG_FILE.exists():
            CONFIG_FILE.unlink()

    def test_save_and_load_provider_config(self):
        save_provider_config(ProviderName.OPENAI, model="gpt-4o")
        
        self.assertTrue(CONFIG_FILE.exists())
        
        import json
        with open(CONFIG_FILE) as f:
            data = json.load(f)
        
        self.assertEqual(data["provider"], "openai")
        self.assertEqual(data["model"], "gpt-4o")

    def test_clear_provider_config(self):
        save_provider_config(ProviderName.ANTHROPIC)
        clear_provider_config()
        
        self.assertFalse(CONFIG_FILE.exists())


class TestAvailableProviders(unittest.TestCase):
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test", "GOOGLE_API_KEY": "test"})
    def test_detects_multiple_providers(self):
        available = get_available_providers()
        self.assertIn(ProviderName.OPENAI, available)
        self.assertIn(ProviderName.GOOGLE, available)

    @patch.dict(os.environ, {}, clear=True)
    def test_returns_empty_when_no_keys(self):
        available = get_available_providers()
        self.assertEqual(available, [])


if __name__ == "__main__":
    unittest.main()