from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import dotenv


class ProviderName(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    AZURE_OPENAI = "azure_openai"
    NONE = "none"


@dataclass
class AIConfig:
    enabled: bool = True
    provider: ProviderName = ProviderName.NONE
    timeout_seconds: int = 30
    model: Optional[str] = None

    @property
    def is_configured(self) -> bool:
        return self.provider != ProviderName.NONE and self.enabled


@dataclass
class ProviderCredentials:
    openai_api_key: Optional[str] = None
    openai_model: Optional[str] = "gpt-4o-mini"
    anthropic_api_key: Optional[str] = None
    anthropic_model: Optional[str] = "claude-3-haiku-20240307"
    google_api_key: Optional[str] = None
    azure_openai_api_key: Optional[str] = None
    azure_openai_endpoint: Optional[str] = None
    azure_openai_deployment: Optional[str] = None
    azure_openai_api_version: Optional[str] = "2024-02-01"


CONFIG_DIR = Path.home() / ".config" / "oss-issue-analyzer"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_dotenv() -> None:
    env_path = Path(".env")
    if env_path.exists():
        dotenv.load_dotenv(env_path)


def ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def get_ai_config() -> AIConfig:
    load_dotenv()
    
    enabled = os.getenv("AI_ENABLED", "true").lower() == "true"
    timeout = int(os.getenv("AI_TIMEOUT_SECONDS", "30"))
    
    provider = ProviderName.NONE
    model = None
    
    if os.getenv("OPENAI_API_KEY"):
        provider = ProviderName.OPENAI
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    elif os.getenv("ANTHROPIC_API_KEY"):
        provider = ProviderName.ANTHROPIC
        model = os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307")
    elif os.getenv("GOOGLE_API_KEY"):
        provider = ProviderName.GOOGLE
        model = None
    elif os.getenv("AZURE_OPENAI_API_KEY") and os.getenv("AZURE_OPENAI_ENDPOINT"):
        provider = ProviderName.AZURE_OPENAI
    
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                saved = json.load(f)
                if saved.get("provider") and saved["provider"] != "none":
                    provider = ProviderName(saved["provider"])
                    model = saved.get("model", model)
        except (json.JSONDecodeError, KeyError):
            pass
    
    return AIConfig(
        enabled=enabled,
        provider=provider,
        timeout_seconds=timeout,
        model=model,
    )


def get_credentials() -> ProviderCredentials:
    load_dotenv()
    
    return ProviderCredentials(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307"),
        google_api_key=os.getenv("GOOGLE_API_KEY"),
        azure_openai_api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        azure_openai_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        azure_openai_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
        azure_openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
    )


def save_provider_config(provider: ProviderName, model: Optional[str] = None) -> None:
    ensure_config_dir()
    config = get_ai_config()
    config.provider = provider
    if model:
        config.model = model
    
    save_data = {
        "provider": provider.value if provider != ProviderName.NONE else "none",
        "model": model,
    }
    
    with open(CONFIG_FILE, "w") as f:
        json.dump(save_data, f, indent=2)


def clear_provider_config() -> None:
    if CONFIG_FILE.exists():
        CONFIG_FILE.unlink()


def get_available_providers() -> list[ProviderName]:
    creds = get_credentials()
    available = []
    
    if creds.openai_api_key:
        available.append(ProviderName.OPENAI)
    if creds.anthropic_api_key:
        available.append(ProviderName.ANTHROPIC)
    if creds.google_api_key:
        available.append(ProviderName.GOOGLE)
    if creds.azure_openai_api_key and creds.azure_openai_endpoint:
        available.append(ProviderName.AZURE_OPENAI)
    
    return available


def test_provider_connection(provider: ProviderName) -> tuple[bool, str]:
    from src.analyzer.llm_provider import (
        get_provider_instance,
    )
    
    try:
        provider_instance = get_provider_instance(provider)
        if provider_instance is None:
            return False, f"Credentials not found for {provider.value}"
        
        result = provider_instance.complete("Say 'test successful' in exactly 3 words.")
        
        if "test successful" in result.lower():
            return True, "Connection successful!"
        else:
            return False, f"Unexpected response: {result[:50]}"
    
    except Exception as e:
        return False, f"Connection failed: {str(e)}"


__all__ = [
    "AIConfig",
    "ProviderName",
    "ProviderCredentials",
    "get_ai_config",
    "get_credentials",
    "save_provider_config",
    "clear_provider_config",
    "get_available_providers",
    "test_provider_connection",
    "CONFIG_DIR",
    "CONFIG_FILE",
]