from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import dotenv


class ProviderName(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    AZURE_OPENAI = "azure_openai"
    NONE = "none"


DEFAULT_CONFIG_DIR = Path.home() / ".config" / "oss-issue-analyzer"


def get_config_dir() -> Path:
    override = os.getenv("OSS_ISSUE_ANALYZER_CONFIG_DIR")
    return Path(override).expanduser() if override else DEFAULT_CONFIG_DIR


def get_config_file() -> Path:
    return get_config_dir() / "config.json"


@dataclass
class AIConfig:
    enabled: bool = True
    provider: ProviderName = ProviderName.NONE
    timeout_seconds: int = 30
    model: Optional[str] = None
    temperature: float = 0.1
    max_tokens: int = 1200
    context_unit_budget: int = 8

    @property
    def is_configured(self) -> bool:
        return self.provider != ProviderName.NONE and self.enabled


@dataclass
class ProviderCredentials:
    openai_api_key: Optional[str] = None
    openai_model: Optional[str] = "gpt-4o-mini"
    anthropic_api_key: Optional[str] = None
    anthropic_model: Optional[str] = "claude-3-5-haiku-20241022"
    google_api_key: Optional[str] = None
    google_model: Optional[str] = "gemini-flash-latest"
    azure_openai_api_key: Optional[str] = None
    azure_openai_endpoint: Optional[str] = None
    azure_openai_deployment: Optional[str] = None
    azure_openai_api_version: Optional[str] = "2024-02-01"


CONFIG_DIR = get_config_dir()
CONFIG_FILE = get_config_file()


def load_dotenv() -> None:
    env_path = Path(".env")
    if env_path.exists():
        dotenv.load_dotenv(env_path)


def ensure_config_dir() -> None:
    get_config_dir().mkdir(parents=True, exist_ok=True)


def _load_saved_config() -> dict[str, Any]:
    config_file = get_config_file()
    if not config_file.exists():
        return {}

    try:
        with open(config_file, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _read_float(name: str, default: float, saved: dict[str, Any]) -> float:
    raw = os.getenv(name, saved.get(name.lower(), default))
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _read_int(name: str, default: int, saved: dict[str, Any]) -> int:
    raw = os.getenv(name, saved.get(name.lower(), default))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def get_ai_config() -> AIConfig:
    load_dotenv()
    saved = _load_saved_config()

    enabled = str(os.getenv("AI_ENABLED", saved.get("enabled", "true"))).lower() == "true"
    timeout = _read_int("AI_TIMEOUT_SECONDS", 30, saved)
    temperature = _read_float("AI_TEMPERATURE", 0.1, saved)
    max_tokens = _read_int("AI_MAX_TOKENS", 1200, saved)
    context_unit_budget = _read_int("AI_CONTEXT_UNIT_BUDGET", 8, saved)

    provider = ProviderName.NONE
    model = None

    if os.getenv("OPENAI_API_KEY"):
        provider = ProviderName.OPENAI
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    elif os.getenv("ANTHROPIC_API_KEY"):
        provider = ProviderName.ANTHROPIC
        model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022")
    elif os.getenv("GOOGLE_API_KEY"):
        provider = ProviderName.GOOGLE
        model = os.getenv("GOOGLE_MODEL", "gemini-flash-latest")
    elif os.getenv("AZURE_OPENAI_API_KEY") and os.getenv("AZURE_OPENAI_ENDPOINT"):
        provider = ProviderName.AZURE_OPENAI
        model = os.getenv("AZURE_OPENAI_DEPLOYMENT")

    saved_provider = saved.get("provider")
    if saved_provider and saved_provider != ProviderName.NONE.value:
        try:
            provider = ProviderName(saved_provider)
            model = saved.get("model", model)
        except ValueError:
            pass

    return AIConfig(
        enabled=enabled,
        provider=provider,
        timeout_seconds=timeout,
        model=model,
        temperature=max(0.0, min(temperature, 1.0)),
        max_tokens=max(256, max_tokens),
        context_unit_budget=max(3, context_unit_budget),
    )


def get_credentials() -> ProviderCredentials:
    load_dotenv()
    saved = _load_saved_config()

    creds = ProviderCredentials(
        openai_api_key=os.getenv("OPENAI_API_KEY") or saved.get("openai_api_key"),
        openai_model=os.getenv("OPENAI_MODEL", saved.get("openai_model", "gpt-4o-mini")),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY") or saved.get("anthropic_api_key"),
        anthropic_model=os.getenv(
            "ANTHROPIC_MODEL",
            saved.get("anthropic_model", "claude-3-5-haiku-20241022"),
        ),
        google_api_key=os.getenv("GOOGLE_API_KEY") or saved.get("google_api_key"),
        google_model=os.getenv("GOOGLE_MODEL", saved.get("google_model", "gemini-flash-latest")),
        azure_openai_api_key=os.getenv("AZURE_OPENAI_API_KEY") or saved.get("azure_openai_api_key"),
        azure_openai_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", saved.get("azure_openai_endpoint")),
        azure_openai_deployment=os.getenv(
            "AZURE_OPENAI_DEPLOYMENT",
            saved.get("azure_openai_deployment"),
        ),
        azure_openai_api_version=os.getenv(
            "AZURE_OPENAI_API_VERSION",
            saved.get("azure_openai_api_version", "2024-02-01"),
        ),
    )
    return creds


def save_provider_config(
    provider: ProviderName,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> None:
    ensure_config_dir()
    ai_config = get_ai_config()
    creds = get_credentials()
    saved = _load_saved_config()

    save_data: dict[str, Any] = {
        **saved,
        "provider": provider.value if provider != ProviderName.NONE else ProviderName.NONE.value,
        "model": model or ai_config.model,
        "enabled": ai_config.enabled,
        "ai_timeout_seconds": ai_config.timeout_seconds,
        "ai_temperature": ai_config.temperature,
        "ai_max_tokens": ai_config.max_tokens,
        "ai_context_unit_budget": ai_config.context_unit_budget,
    }

    if not api_key:
        if provider == ProviderName.OPENAI:
            api_key = creds.openai_api_key
            save_data["openai_model"] = save_data["model"] or creds.openai_model
        elif provider == ProviderName.ANTHROPIC:
            api_key = creds.anthropic_api_key
            save_data["anthropic_model"] = save_data["model"] or creds.anthropic_model
        elif provider == ProviderName.GOOGLE:
            api_key = creds.google_api_key
            save_data["google_model"] = creds.google_model
        elif provider == ProviderName.AZURE_OPENAI:
            api_key = creds.azure_openai_api_key
            save_data["azure_openai_endpoint"] = creds.azure_openai_endpoint
            save_data["azure_openai_deployment"] = creds.azure_openai_deployment
            save_data["azure_openai_api_version"] = creds.azure_openai_api_version

    if provider == ProviderName.OPENAI and api_key:
        save_data["openai_api_key"] = api_key
    elif provider == ProviderName.ANTHROPIC and api_key:
        save_data["anthropic_api_key"] = api_key
    elif provider == ProviderName.GOOGLE and api_key:
        save_data["google_api_key"] = api_key
    elif provider == ProviderName.AZURE_OPENAI:
        if api_key:
            save_data["azure_openai_api_key"] = api_key
        if creds.azure_openai_endpoint:
            save_data["azure_openai_endpoint"] = creds.azure_openai_endpoint
        if creds.azure_openai_deployment:
            save_data["azure_openai_deployment"] = creds.azure_openai_deployment

    with open(get_config_file(), "w", encoding="utf-8") as handle:
        json.dump(save_data, handle, indent=2)


def clear_provider_config() -> None:
    config_file = get_config_file()
    if config_file.exists():
        config_file.unlink()


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
    from src.analyzer.llm_provider import LLMRequest, get_provider_instance

    try:
        provider_instance = get_provider_instance(provider)
        if provider_instance is None:
            return False, f"Credentials not found for {provider.value}"

        response = provider_instance.complete(
            LLMRequest(
                system="You are a connection test helper.",
                user="Say 'test successful' in exactly 3 words.",
                temperature=0.0,
                max_tokens=32,
            )
        )

        result_lower = response.content.lower()
        if "test" in result_lower and "successful" in result_lower:
            return True, "Connection successful!"
        return False, f"Unexpected response: {response.content[:50]}"
    except Exception as exc:
        return False, f"Connection failed: {exc}"


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
    "get_config_dir",
    "get_config_file",
    "CONFIG_DIR",
    "CONFIG_FILE",
]
