from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

from src.analyzer.config import ProviderName, get_credentials


@dataclass
class LLMRequest:
    system: str
    user: str
    temperature: float = 0.1
    max_tokens: int = 1200
    response_format: Optional[dict[str, Any]] = None


@dataclass
class LLMResponse:
    content: str
    raw_response: Optional[object] = None
    model: Optional[str] = None
    tokens_used: Optional[int] = None


class LLMProvider(ABC):
    @abstractmethod
    def complete(self, request: LLMRequest) -> LLMResponse:
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        pass

    def close(self) -> None:
        pass


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        from openai import OpenAI

        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key not provided")

        self.model = model
        self.client = OpenAI(api_key=self.api_key)

    def complete(self, request: LLMRequest) -> LLMResponse:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            response_format=request.response_format,
        )
        content = response.choices[0].message.content or ""
        tokens_used = getattr(getattr(response, "usage", None), "total_tokens", None)
        return LLMResponse(content=content, raw_response=response, model=self.model, tokens_used=tokens_used)

    def get_provider_name(self) -> str:
        return "openai"

    def get_model_name(self) -> str:
        return self.model


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: Optional[str] = None, model: str = "claude-3-5-haiku-20241022"):
        import anthropic

        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("Anthropic API key not provided")

        self.model = model
        self.client = anthropic.Anthropic(api_key=self.api_key)

    def complete(self, request: LLMRequest) -> LLMResponse:
        message = self.client.messages.create(
            model=self.model,
            system=request.system,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            messages=[{"role": "user", "content": request.user}],
        )
        content_parts = getattr(message, "content", []) or []
        content = "".join(getattr(part, "text", "") for part in content_parts)
        usage = getattr(message, "usage", None)
        tokens_used = None
        if usage is not None:
            tokens_used = getattr(usage, "input_tokens", 0) + getattr(usage, "output_tokens", 0)
        return LLMResponse(content=content, raw_response=message, model=self.model, tokens_used=tokens_used)

    def get_provider_name(self) -> str:
        return "anthropic"

    def get_model_name(self) -> str:
        return self.model


class GoogleProvider(LLMProvider):
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-flash-latest"):
        try:
            from google import genai
        except ImportError as exc:
            raise ImportError("Please install google-genai: pip install google-genai") from exc

        self.api_key = api_key or get_credentials().google_api_key
        if not self.api_key:
            raise ValueError("Google API key not provided")

        self.model_name = model
        self.client = genai.Client(api_key=self.api_key)

    def complete(self, request: LLMRequest) -> LLMResponse:
        config = {
            "temperature": request.temperature,
            "max_output_tokens": request.max_tokens,
        }
        if request.response_format:
            config["response_mime_type"] = "application/json"
        if request.system:
            config["system_instruction"] = request.system

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=request.user,
                config=config,
            )
        except TypeError:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=f"{request.system}\n\n{request.user}",
            )

        text = getattr(response, "text", "") or ""
        usage = getattr(response, "usage_metadata", None)
        tokens_used = getattr(usage, "total_token_count", None) if usage else None
        return LLMResponse(content=text, raw_response=response, model=self.model_name, tokens_used=tokens_used)

    def get_provider_name(self) -> str:
        return "google"

    def get_model_name(self) -> str:
        return self.model_name


class AzureOpenAIProvider(LLMProvider):
    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        deployment: Optional[str] = None,
        api_version: str = "2024-02-01",
    ):
        from openai import AzureOpenAI

        self.api_key = api_key or os.getenv("AZURE_OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("Azure OpenAI API key not provided")

        self.endpoint = endpoint or os.getenv("AZURE_OPENAI_ENDPOINT")
        if not self.endpoint:
            raise ValueError("Azure OpenAI endpoint not provided")

        self.deployment = deployment or os.getenv("AZURE_OPENAI_DEPLOYMENT")
        self.api_version = api_version
        self.client = AzureOpenAI(
            api_key=self.api_key,
            azure_endpoint=self.endpoint,
            api_version=self.api_version,
        )

    def complete(self, request: LLMRequest) -> LLMResponse:
        model = self.deployment or "gpt-4o-mini"
        response = self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            response_format=request.response_format,
        )
        content = response.choices[0].message.content or ""
        tokens_used = getattr(getattr(response, "usage", None), "total_tokens", None)
        return LLMResponse(content=content, raw_response=response, model=model, tokens_used=tokens_used)

    def get_provider_name(self) -> str:
        return "azure_openai"

    def get_model_name(self) -> str:
        return self.deployment or "azure-deployment"


class MockProvider(LLMProvider):
    def __init__(self, response: str = "AI analysis complete"):
        self._response = response

    def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(content=self._response, model="mock-model")

    def get_provider_name(self) -> str:
        return "mock"

    def get_model_name(self) -> str:
        return "mock-model"


def get_provider_instance(
    provider: ProviderName,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> Optional[LLMProvider]:
    if provider == ProviderName.NONE:
        return None

    creds = get_credentials()
    if provider == ProviderName.OPENAI:
        key = api_key or creds.openai_api_key
        if not key:
            return None
        return OpenAIProvider(api_key=key, model=model or creds.openai_model or "gpt-4o-mini")

    if provider == ProviderName.ANTHROPIC:
        key = api_key or creds.anthropic_api_key
        if not key:
            return None
        return AnthropicProvider(
            api_key=key,
            model=model or creds.anthropic_model or "claude-3-5-haiku-20241022",
        )

    if provider == ProviderName.GOOGLE:
        key = api_key or creds.google_api_key
        if not key:
            return None
        return GoogleProvider(api_key=key, model=model or creds.google_model or "gemini-flash-latest")

    if provider == ProviderName.AZURE_OPENAI:
        key = api_key or creds.azure_openai_api_key
        endpoint = creds.azure_openai_endpoint
        if not key or not endpoint:
            return None
        return AzureOpenAIProvider(
            api_key=key,
            endpoint=endpoint,
            deployment=model or creds.azure_openai_deployment,
            api_version=creds.azure_openai_api_version or "2024-02-01",
        )

    return None


__all__ = [
    "LLMRequest",
    "LLMProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "GoogleProvider",
    "AzureOpenAIProvider",
    "MockProvider",
    "get_provider_instance",
    "LLMResponse",
]
