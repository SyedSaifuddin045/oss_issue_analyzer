from __future__ import annotations
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class IssueType(str, Enum):
    BUG = "bug"
    FEATURE = "feature"
    REFACTOR = "refactor"
    DOCS = "docs"
    TEST = "test"
    UNKNOWN = "unknown"


@dataclass
class ExtractedFile:
    path: str
    line_hint: Optional[int] = None
    is_exact: bool = True


@dataclass
class ExtractedSymbol:
    name: str
    context: str = ""


@dataclass
class ExtractedError:
    pattern: str
    file_hint: Optional[str] = None
    line_hint: Optional[int] = None


@dataclass
class ProcessedIssue:
    title: str
    body: str
    issue_type: IssueType = IssueType.UNKNOWN
    mentioned_files: list[ExtractedFile] = field(default_factory=list)
    mentioned_symbols: list[ExtractedSymbol] = field(default_factory=list)
    error_patterns: list[ExtractedError] = field(default_factory=list)
    searchable_text: str = ""


class IssuePreprocessor:
    FILE_PATH_PATTERNS = [
        # src/utils/foo.py
        r"(?:src|lib|app|packages?)/[\w/.-]+\.\w+",
        # django/utils/timezone.py
        r"(?:django|flask|requests|pytest|numpy|pandas)[\w/]*\.\w+",
        # /path/to/file.py
        r"(?:\/[\w.-]+)+/[\w.-]+\.\w+",
        # foo.py (with extension only, context-dependent)
        r"(?<![a-zA-Z0-9_/])[\w-]+\.(?:py|js|ts|jsx|tsx|go|rs|java|cpp|c|h)\b",
    ]

    FUNCTION_PATTERNS = [
        # function_name(
        r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(",
        # def function_name
        r"(?:def|func|fn|function)\s+([a-zA-Z_][a-zA-Z0-9_]*)",
        # class ClassName
        r"(?:class|struct|interface)\s+([a-zA-Z_][a-zA-Z0-9_]*)",
    ]

    STACK_TRACE_PATTERNS = [
        # Python
        r'File\s+"([^"]+)",\s+line\s+(\d+)',
        # JavaScript
        r"(?:at\s+)?([^\s]+)\s*\[(?:native\s+)?code?\]\s*at\s+([^\s]+):(\d+)",
        # Generic
        r"([\w.]+):(\d+):(\d+)",
    ]

    ISSUE_TYPE_KEYWORDS = {
        IssueType.BUG: [
            "bug", "fix", "error", "exception", "wrong", "incorrect", "fails",
            "broken", "issue", "crash", "panic", "debug", "defect"
        ],
        IssueType.FEATURE: [
            "feature", "add", "implement", "new", "support", "enhance",
            "improve", "capability", "option"
        ],
        IssueType.REFACTOR: [
            "refactor", "cleanup", "clean up", "restructure", "simplify",
            "optimize", "modernize", "deprecate"
        ],
        IssueType.DOCS: [
            "docs", "document", "documentation", "readme", "comment",
            "example", "guide", "tutorial"
        ],
        IssueType.TEST: [
            "test", "spec", "unittest", "coverage", "assert",
            "mock", "fixture", "scenario"
        ],
    }

    def process(self, title: str, body: str) -> ProcessedIssue:
        cleaned_title = self._clean_text(title)
        cleaned_body = self._clean_text(body)
        
        issue_type = self._classify_issue_type(cleaned_title, cleaned_body)
        mentioned_files = self._extract_file_mentions(cleaned_title + "\n" + cleaned_body)
        mentioned_symbols = self._extract_symbol_mentions(cleaned_title + "\n" + cleaned_body)
        error_patterns = self._extract_error_patterns(cleaned_body)
        
        searchable_text = self._build_searchable_text(
            cleaned_title, cleaned_body, mentioned_files, mentioned_symbols
        )

        return ProcessedIssue(
            title=cleaned_title,
            body=cleaned_body,
            issue_type=issue_type,
            mentioned_files=mentioned_files,
            mentioned_symbols=mentioned_symbols,
            error_patterns=error_patterns,
            searchable_text=searchable_text,
        )

    def _clean_text(self, text: str) -> str:
        if not text:
            return ""
        
        text = re.sub(r"```[\w]*\n[\s\S]*?```", "", text)
        text = re.sub(r"`[^`]+`", "", text)
        text = re.sub(r"<!--[\s\S]*?-->", "", text)
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        text = re.sub(r"#+", "#", text)
        
        lines = []
        for line in text.split("\n"):
            line = line.strip()
            if line and not line.startswith(">"):
                lines.append(line)
        
        return "\n".join(lines)

    def _classify_issue_type(self, title: str, body: str) -> IssueType:
        full_text = (title + " " + body).lower()
        
        best_match = IssueType.UNKNOWN
        best_score = 0

        for issue_type, keywords in self.ISSUE_TYPE_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in full_text)
            if score > best_score:
                best_score = score
                best_match = issue_type

        return best_match

    def _extract_file_mentions(self, text: str) -> list[ExtractedFile]:
        files = []
        seen = set()

        for pattern in self.FILE_PATH_PATTERNS:
            for match in re.finditer(pattern, text):
                path = match.group(0)
                if path not in seen and len(path) > 3:
                    seen.add(path)
                    files.append(ExtractedFile(path=path, is_exact=True))

        return files

    def _extract_symbol_mentions(self, text: str) -> list[ExtractedSymbol]:
        symbols = []
        seen = set()

        for pattern in self.FUNCTION_PATTERNS:
            for match in re.finditer(pattern, text):
                name = match.group(1)
                if name and name not in seen and len(name) > 2:
                    seen.add(name)
                    context_start = max(0, match.start() - 20)
                    context = text[context_start:match.start() + 20]
                    symbols.append(ExtractedSymbol(name=name, context=context))

        return symbols

    def _extract_error_patterns(self, text: str) -> list[ExtractedError]:
        errors = []

        for pattern in self.STACK_TRACE_PATTERNS:
            for match in re.finditer(pattern, text):
                groups = match.groups()
                if groups:
                    pattern_str = ":".join(str(g) for g in groups if g)
                    errors.append(ExtractedError(pattern=pattern_str))

        return errors[:5]

    def _build_searchable_text(
        self,
        title: str,
        body: str,
        files: list[ExtractedFile],
        symbols: list[ExtractedSymbol],
    ) -> str:
        parts = [title]
        if body:
            parts.append(body)
        
        for f in files:
            parts.append(f.path)
        
        for s in symbols:
            parts.append(s.name)

        return " | ".join(parts)


__all__ = [
    "IssueType",
    "ExtractedFile",
    "ExtractedSymbol",
    "ExtractedError",
    "ProcessedIssue",
    "IssuePreprocessor",
]