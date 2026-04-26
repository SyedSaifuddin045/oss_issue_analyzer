from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from src.analyzer.config import (
    ProviderName,
    get_credentials,
)


@dataclass
class LLMResponse:
    content: str
    raw_response: Optional[object] = None
    model: Optional[str] = None
    tokens_used: Optional[int] = None


class LLMProvider(ABC):
    @abstractmethod
    def complete(self, prompt: str, **kwargs) -> str:
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

    def complete(self, prompt: str, **kwargs) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            **kwargs
        )
        return response.choices[0].message.content

    def get_provider_name(self) -> str:
        return "openai"

    def get_model_name(self) -> str:
        return self.model


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: Optional[str] = None, model: str = "claude-3-haiku-20240307"):
        import anthropic
        
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("Anthropic API key not provided")
        
        self.model = model
        self.client = anthropic.Anthropic(api_key=self.api_key)

    def complete(self, prompt: str, **kwargs) -> str:
        message = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
            **kwargs
        )
        return message.content[0].text

    def get_provider_name(self) -> str:
        return "anthropic"

    def get_model_name(self) -> str:
        return self.model


class GoogleProvider(LLMProvider):
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-1.5-flash"):
        import google.generativeai as genai
        
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("Google API key not provided")
        
        genai.configure(api_key=self.api_key)
        self.model_name = model
        self.model = genai.GenerativeModel(model)

    def complete(self, prompt: str, **kwargs) -> str:
        generation_config = {
            "temperature": 0.7,
            **kwargs
        }
        response = self.model.generate_content(
            prompt,
            generation_config=generation_config
        )
        return response.text

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
        api_version: str = "2024-02-01"
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

    def complete(self, prompt: str, **kwargs) -> str:
        model = self.deployment or "gpt-4o-mini"
        response = self.client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            **kwargs
        )
        return response.choices[0].message.content

    def get_provider_name(self) -> str:
        return "azure_openai"

    def get_model_name(self) -> str:
        return self.deployment or "azure-deployment"


class MockProvider(LLMProvider):
    def __init__(self, response: str = "AI analysis complete"):
        self._response = response

    def complete(self, prompt: str, **kwargs) -> str:
        return self._response

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
    
    if provider == ProviderName.OPENAI:
        creds = get_credentials()
        key = api_key or creds.openai_api_key
        if not key:
            return None
        return OpenAIProvider(
            api_key=key,
            model=model or creds.openai_model or "gpt-4o-mini"
        )
    
    if provider == ProviderName.ANTHROPIC:
        creds = get_credentials()
        key = api_key or creds.anthropic_api_key
        if not key:
            return None
        return AnthropicProvider(
            api_key=key,
            model=model or creds.anthropic_model or "claude-3-haiku-20240307"
        )
    
    if provider == ProviderName.GOOGLE:
        creds = get_credentials()
        key = api_key or creds.google_api_key
        if not key:
            return None
        return GoogleProvider(
            api_key=key,
        )
    
    if provider == ProviderName.AZURE_OPENAI:
        creds = get_credentials()
        key = api_key or creds.azure_openai_api_key
        endpoint = creds.azure_openai_endpoint
        if not key or not endpoint:
            return None
        return AzureOpenAIProvider(
            api_key=key,
            endpoint=endpoint,
            deployment=creds.azure_openai_deployment,
            api_version=creds.azure_openai_api_version or "2024-02-01",
        )
    
    return None


__all__ = [
    "LLMProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "GoogleProvider",
    "AzureOpenAIProvider",
    "MockProvider",
    "get_provider_instance",
    "LLMResponse",
]