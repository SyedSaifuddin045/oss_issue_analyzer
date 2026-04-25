from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from tree_sitter import Language, Node, Parser


class UnitType(str, Enum):
    FILE = "file"
    DIRECTORY = "directory"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    MODULE = "module"
    DOCUMENT = "document"
    CONFIG = "config"


class AssetKind(str, Enum):
    CODE = "code"
    CONFIG = "config"
    DOCS = "docs"
    WORKFLOW = "workflow"


@dataclass
class ParsedUnit:
    id: str
    repo_id: str
    unit_type: UnitType
    path: str
    language: str
    start_line: int
    end_line: int
    signature: Optional[str] = None
    docstring: Optional[str] = None
    code: str = ""
    name: str = ""
    parent_name: Optional[str] = None
    asset_kind: AssetKind = AssetKind.CODE
    children: list[ParsedUnit] = field(default_factory=list)


class LanguageParser(ABC):
    @property
    @abstractmethod
    def language(self) -> str:
        """Language identifier (e.g., 'python', 'javascript')."""
        ...

    @property
    @abstractmethod
    def file_extensions(self) -> list[str]:
        """Supported file extensions (e.g., ['.py'])."""
        ...

    @property
    @abstractmethod
    def language_binding(self) -> Language:
        """Tree-sitter Language object."""
        ...

    def parse_file(self, source: str, file_path: str, repo_id: str) -> ParsedUnit:
        """Parse a file and return a hierarchical structure of code units."""
        parser = Parser()
        parser.language = self.language_binding
        tree = parser.parse(source.encode())
        return self._build_unit_tree(tree.root_node, source, file_path, repo_id)

    def _build_unit_tree(
        self, node: Node, source: str, file_path: str, repo_id: str, parent: Optional[ParsedUnit] = None
    ) -> ParsedUnit:
        node_type = node.type
        start_line = node.start_point.row + 1
        end_line = node.end_point.row + 1
        code = self._extract_code(source, node)

        name = self._extract_name(node)
        signature = self._extract_signature(node, source)
        docstring = self._extract_docstring(node, source)
        unit_type = self._map_node_type(node_type)

        unit_id = self._generate_unit_id(repo_id, file_path, start_line, end_line, name)

        unit = ParsedUnit(
            id=unit_id,
            repo_id=repo_id,
            unit_type=unit_type,
            path=file_path,
            language=self.language,
            start_line=start_line,
            end_line=end_line,
            signature=signature,
            docstring=docstring,
            code=code,
            name=name,
            parent_name=parent.name if parent else None,
        )

        for child in node.children:
            child_unit = self._build_unit_tree(child, source, file_path, repo_id, unit)
            if child_unit.unit_type != UnitType.FILE:
                unit.children.append(child_unit)

        return unit

    def _extract_code(self, source: str, node: Node) -> str:
        lines = source.split("\n")
        if node.start_point.row == node.end_point.row:
            return lines[node.start_point.row][node.start_point.column : node.end_point.column]
        code_lines = lines[node.start_point.row : node.end_point.row + 1]
        code_lines[0] = code_lines[0][node.start_point.column :]
        code_lines[-1] = code_lines[-1][: node.end_point.column]
        return "\n".join(code_lines)

    def _extract_name(self, node: Node) -> str:
        return ""

    def _extract_signature(self, node: Node, source: str) -> Optional[str]:
        return None

    def _extract_docstring(self, node: Node, source: str) -> Optional[str]:
        return None

    def _generate_unit_id(
        self, repo_id: str, path: str, start_line: int, end_line: int, name: str
    ) -> str:
        return f"{repo_id}:{path}:{start_line}-{end_line}:{name}"

    def _map_node_type(self, node_type: str) -> UnitType:
        return UnitType.FILE


class MultiLanguageParser:
    LANGUAGE_MAP: dict[str, type[LanguageParser]] = {}

    @classmethod
    def _ensure_registered(cls) -> None:
        if cls.LANGUAGE_MAP:
            return
        from src.indexer import languages  # noqa: F401

    @classmethod
    def register(cls, parser_class: type[LanguageParser]) -> None:
        instance = parser_class()
        cls.LANGUAGE_MAP[instance.language] = parser_class

    @classmethod
    def for_language(cls, language: str) -> Optional[LanguageParser]:
        cls._ensure_registered()
        parser_class = cls.LANGUAGE_MAP.get(language.lower())
        if parser_class:
            return parser_class()
        return None

    @classmethod
    def for_extension(cls, ext: str) -> Optional[LanguageParser]:
        cls._ensure_registered()
        ext = ext if ext.startswith(".") else f".{ext}"
        for parser in cls.LANGUAGE_MAP.values():
            if ext in parser().file_extensions:
                return parser()
        return None

    @classmethod
    def supported_languages(cls) -> list[str]:
        cls._ensure_registered()
        return list(cls.LANGUAGE_MAP.keys())

    @classmethod
    def supported_extensions(cls) -> list[str]:
        cls._ensure_registered()
        extensions = set()
        for parser in cls.LANGUAGE_MAP.values():
            extensions.update(parser().file_extensions)
        return sorted(extensions)


def get_parser(language: str) -> Optional[LanguageParser]:
    return MultiLanguageParser.for_language(language)


def get_parser_for_file(file_path: str) -> Optional[LanguageParser]:
    ext = Path(file_path).suffix
    return MultiLanguageParser.for_extension(ext)


__all__ = [
    "UnitType",
    "AssetKind",
    "ParsedUnit",
    "LanguageParser",
    "MultiLanguageParser",
    "get_parser",
    "get_parser_for_file",
]
