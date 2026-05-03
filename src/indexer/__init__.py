from __future__ import annotations

import importlib

from src.indexer.parser import (
    AssetKind,
    LanguageParser,
    MultiLanguageParser,
    ParsedUnit,
    UnitType,
    get_parser,
    get_parser_for_file,
)

__all__ = [
    "UnitType",
    "AssetKind",
    "ParsedUnit",
    "LanguageParser",
    "MultiLanguageParser",
    "PythonParser",
    "JavaScriptParser",
    "TypeScriptParser",
    "GoParser",
    "RustParser",
    "JavaParser",
    "CParser",
    "CppParser",
    "get_parser",
    "get_parser_for_file",
    "Embedder",
    "LocalNomicEmbedder",
    "MiniLMEmbedder",
    "get_embedder",
    "VectorStore",
    "CodeUnit",
    "Repository",
    "get_index",
    "CodeIndexer",
    "IndexerConfig",
    "index_repository",
    "DependencyAnalyzer",
    "DependencyProfile",
]


def __getattr__(name: str):
    if name in {
        "PythonParser",
        "JavaScriptParser",
        "TypeScriptParser",
        "GoParser",
        "RustParser",
        "JavaParser",
        "CParser",
        "CppParser",
    }:
        module = importlib.import_module("src.indexer.languages")
        return getattr(module, name)
    if name in {"DependencyAnalyzer", "DependencyProfile"}:
        module = importlib.import_module("src.indexer.dependencies")
        return getattr(module, name)
    if name in {"Embedder", "LocalNomicEmbedder", "MiniLMEmbedder", "get_embedder"}:
        module = importlib.import_module("src.indexer.embedder")
        return getattr(module, name)
    if name in {"VectorStore", "CodeUnit", "Repository", "get_index"}:
        module = importlib.import_module("src.indexer.storage")
        return getattr(module, name)
    if name in {"CodeIndexer", "IndexerConfig", "index_repository"}:
        module = importlib.import_module("src.indexer.indexer")
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
