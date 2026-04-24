from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional

import numpy as np
import torch
from sentence_transformers import SentenceTransformer


class Embedder(ABC):
    @property
    @abstractmethod
    def dimension(self) -> int:
        """Embedding dimension."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Model identifier."""
        ...

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Generate embedding for a single text."""
        ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        ...


class LocalNomicEmbedder(Embedder):
    DEFAULT_MODEL = "nomic-ai/CodeRankEmbed"

    def __init__(self, model_name: Optional[str] = None, device: Optional[str] = None):
        self._model_name = model_name or self.DEFAULT_MODEL
        self._device = device or self._get_default_device()
        self._model: Optional[SentenceTransformer] = None
        self._cached_dimension: Optional[int] = None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        if self._cached_dimension is None:
            self._ensure_model_loaded()
            self._cached_dimension = self._model.get_sentence_embedding_dimension()
        return self._cached_dimension

    def _get_default_device(self) -> str:
        if torch.cuda.is_available():
            return "cuda"
        return "cpu"

    def _ensure_model_loaded(self) -> None:
        if self._model is None:
            try:
                self._model = SentenceTransformer(
                    self._model_name,
                    device=self._device,
                    trust_remote_code=True,
                )
            except TypeError:
                self._model = SentenceTransformer(
                    self._model_name,
                    device=self._device,
                    trust_remote_code=True,
                    model_kwargs={"safe_serialization": False},
                )

    def embed(self, text: str) -> list[float]:
        self._ensure_model_loaded()
        embedding = self._model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        self._ensure_model_loaded()
        embeddings = self._model.encode(
            texts,
            normalize_embeddings=True,
            batch_size=32,
            show_progress_bar=False,
        )
        return embeddings.tolist()


class MiniLMEmbedder(Embedder):
    DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

    def __init__(self, model_name: Optional[str] = None, device: Optional[str] = None):
        self._model_name = model_name or self.DEFAULT_MODEL
        self._device = device or self._get_default_device()
        self._model: Optional[SentenceTransformer] = None
        self._cached_dimension: Optional[int] = None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        if self._cached_dimension is None:
            self._ensure_model_loaded()
            self._cached_dimension = self._model.get_sentence_embedding_dimension()
        return self._cached_dimension

    def _get_default_device(self) -> str:
        if torch.cuda.is_available():
            return "cuda"
        return "cpu"

    def _ensure_model_loaded(self) -> None:
        if self._model is None:
            self._model = SentenceTransformer(
                self._model_name,
                device=self._device,
            )

    def embed(self, text: str) -> list[float]:
        self._ensure_model_loaded()
        embedding = self._model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        self._ensure_model_loaded()
        embeddings = self._model.encode(
            texts,
            normalize_embeddings=True,
            batch_size=32,
            show_progress_bar=False,
        )
        return embeddings.tolist()


def get_embedder(
    model: str = "nomic",
    device: Optional[str] = None,
) -> Embedder:
    """Factory function to get an embedder by name."""
    if model == "nomic":
        return LocalNomicEmbedder(device=device)
    elif model == "minilm":
        return MiniLMEmbedder(device=device)
    else:
        return LocalNomicEmbedder(model, device=device)


__all__ = [
    "Embedder",
    "LocalNomicEmbedder",
    "MiniLMEmbedder",
    "get_embedder",
]