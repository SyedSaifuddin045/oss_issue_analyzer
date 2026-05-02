from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.analyzer import config as config_module
from src.analyzer.config import (
    AIConfig,
    ProviderName,
    clear_provider_config,
    get_ai_config,
    get_available_providers,
    get_config_file,
    get_credentials,
    save_provider_config,
)


class ConfigTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.base_env = {"OSS_ISSUE_ANALYZER_CONFIG_DIR": self.temp_dir.name}

    def tearDown(self):
        self.temp_dir.cleanup()

    def config_file(self) -> Path:
        return Path(self.temp_dir.name) / "config.json"


class TestConfigLoading(ConfigTestCase):
    def test_get_credentials_loads_from_env(self):
        with patch.dict(os.environ, {**self.base_env, "OPENAI_API_KEY": "test-key-123"}, clear=True):
            creds = get_credentials()
            self.assertEqual(creds.openai_api_key, "test-key-123")

    def test_get_credentials_google(self):
        with patch.dict(os.environ, {**self.base_env, "GOOGLE_API_KEY": "google-test-key"}, clear=True):
            creds = get_credentials()
            self.assertEqual(creds.google_api_key, "google-test-key")
            self.assertEqual(creds.google_model, "gemini-flash-latest")

    def test_ai_disabled_via_env(self):
        with patch.dict(os.environ, {**self.base_env, "AI_ENABLED": "false"}, clear=True):
            config = get_ai_config()
            self.assertFalse(config.enabled)

    def test_custom_analysis_settings(self):
        with patch.dict(
            os.environ,
            {
                **self.base_env,
                "AI_TIMEOUT_SECONDS": "60",
                "AI_TEMPERATURE": "0.25",
                "AI_MAX_TOKENS": "2048",
                "AI_CONTEXT_UNIT_BUDGET": "11",
            },
            clear=True,
        ):
            config = get_ai_config()
            self.assertEqual(config.timeout_seconds, 60)
            self.assertEqual(config.temperature, 0.25)
            self.assertEqual(config.max_tokens, 2048)
            self.assertEqual(config.context_unit_budget, 11)


class TestProviderSelection(ConfigTestCase):
    def test_auto_detect_openai_provider(self):
        with patch.dict(os.environ, {**self.base_env, "OPENAI_API_KEY": "test-key"}, clear=True):
            config = get_ai_config()
            self.assertEqual(config.provider, ProviderName.OPENAI)

    def test_preference_order_openai_over_google(self):
        with patch.dict(
            os.environ,
            {**self.base_env, "OPENAI_API_KEY": "test-key", "GOOGLE_API_KEY": "test-key"},
            clear=True,
        ):
            config = get_ai_config()
            self.assertEqual(config.provider, ProviderName.OPENAI)

    def test_no_provider_when_no_keys(self):
        with patch.dict(os.environ, self.base_env, clear=True):
            config = get_ai_config()
            self.assertEqual(config.provider, ProviderName.NONE)

    def test_is_configured_returns_false_when_disabled(self):
        config = AIConfig(enabled=False, provider=ProviderName.OPENAI)
        self.assertFalse(config.is_configured)

    def test_is_configured_returns_true_when_configured(self):
        config = AIConfig(enabled=True, provider=ProviderName.OPENAI)
        self.assertTrue(config.is_configured)


class TestSaveProviderConfig(ConfigTestCase):
    def test_save_and_load_provider_config(self):
        with patch.dict(os.environ, self.base_env, clear=True):
            save_provider_config(ProviderName.OPENAI, model="gpt-4o")
            self.assertTrue(get_config_file().exists())

            with open(get_config_file(), encoding="utf-8") as handle:
                data = json.load(handle)

            self.assertEqual(data["provider"], "openai")
            self.assertEqual(data["model"], "gpt-4o")
            self.assertIn("ai_temperature", data)

    def test_clear_provider_config(self):
        with patch.dict(os.environ, self.base_env, clear=True):
            save_provider_config(ProviderName.ANTHROPIC)
            clear_provider_config()
            self.assertFalse(get_config_file().exists())


class TestAvailableProviders(ConfigTestCase):
    def test_detects_multiple_providers(self):
        with patch.dict(
            os.environ,
            {**self.base_env, "OPENAI_API_KEY": "test", "GOOGLE_API_KEY": "test"},
            clear=True,
        ):
            available = get_available_providers()
            self.assertIn(ProviderName.OPENAI, available)
            self.assertIn(ProviderName.GOOGLE, available)

    def test_returns_empty_when_no_keys(self):
        with patch.dict(os.environ, self.base_env, clear=True):
            self.assertEqual(get_available_providers(), [])


if __name__ == "__main__":
    unittest.main()
