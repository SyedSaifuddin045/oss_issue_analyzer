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
class IssueCommentContext:
    body: str
    author: str = "unknown"
    is_maintainer: bool = False
    reactions: int = 0


@dataclass
class ProcessedIssue:
    title: str
    body: str
    issue_type: IssueType = IssueType.UNKNOWN
    mentioned_files: list[ExtractedFile] = field(default_factory=list)
    mentioned_symbols: list[ExtractedSymbol] = field(default_factory=list)
    error_patterns: list[ExtractedError] = field(default_factory=list)
    searchable_text: str = ""
    comments: list[IssueCommentContext] = field(default_factory=list)
    code_blocks: list[str] = field(default_factory=list)
    stack_traces: list[str] = field(default_factory=list)


class IssuePreprocessor:
    FILE_PATH_PATTERNS = [
        r"(?:src|lib|app|packages?|tests?)/[\w/.-]+\.\w+",
        r"(?:django|flask|requests|pytest|numpy|pandas)[\w/]*\.\w+",
        r"(?:\/[\w.-]+)+/[\w.-]+\.\w+",
        r"(?<![a-zA-Z0-9_/])[\w-]+\.(?:py|js|ts|jsx|tsx|go|rs|java|cpp|c|h|md|toml|ya?ml)\b",
    ]

    FUNCTION_PATTERNS = [
        r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(",
        r"(?:def|func|fn|function)\s+([a-zA-Z_][a-zA-Z0-9_]*)",
        r"(?:class|struct|interface)\s+([a-zA-Z_][a-zA-Z0-9_]*)",
    ]

    SYMBOL_PATTERNS = [
        r"\b([a-zA-Z]+_[a-zA-Z0-9_]+)\b",
        r"\b([a-z]+(?:[A-Z][a-z0-9]+)+)\b",
        r"\b([A-Z][a-zA-Z0-9]+(?:Error|Exception|Warning))\b",
    ]

    STACK_TRACE_PATTERNS = [
        r'File\s+"([^"]+)",\s+line\s+(\d+)',
        r"(?:at\s+)?([^\s]+)\s*\[(?:native\s+)?code?\]\s*at\s+([^\s]+):(\d+)",
        r"([\w./-]+):(\d+):(\d+)",
    ]

    CODE_BLOCK_RE = re.compile(r"```[\w+-]*\n([\s\S]*?)```", re.MULTILINE)

    ISSUE_TYPE_KEYWORDS = {
        IssueType.BUG: [
            "bug", "fix", "error", "exception", "wrong", "incorrect", "fails",
            "broken", "issue", "crash", "panic", "debug", "defect", "traceback",
        ],
        IssueType.FEATURE: [
            "feature", "add", "implement", "new", "support", "enhance",
            "improve", "capability", "option",
        ],
        IssueType.REFACTOR: [
            "refactor", "cleanup", "clean up", "restructure", "simplify",
            "optimize", "modernize", "deprecate",
        ],
        IssueType.DOCS: [
            "docs", "document", "documentation", "readme", "comment",
            "example", "guide", "tutorial",
        ],
        IssueType.TEST: [
            "test", "spec", "unittest", "coverage", "assert",
            "mock", "fixture", "scenario", "pytest",
        ],
    }

    def process(self, title: str, body: str) -> ProcessedIssue:
        code_blocks = self._extract_code_blocks(body)
        stack_traces = self._extract_stack_traces(body)
        cleaned_title = self._clean_text(title)
        cleaned_body = self._clean_text(body, code_blocks=code_blocks)

        issue_type = self._classify_issue_type(cleaned_title, cleaned_body)
        combined_text = "\n".join(filter(None, [cleaned_title, cleaned_body, *code_blocks, *stack_traces]))
        mentioned_files = self._extract_file_mentions(combined_text)
        mentioned_symbols = self._extract_symbol_mentions(combined_text)
        error_patterns = self._extract_error_patterns(body)

        searchable_text = self._build_searchable_text(
            cleaned_title,
            cleaned_body,
            mentioned_files,
            mentioned_symbols,
            code_blocks,
            stack_traces,
            error_patterns,
        )

        return ProcessedIssue(
            title=cleaned_title,
            body=cleaned_body,
            issue_type=issue_type,
            mentioned_files=mentioned_files,
            mentioned_symbols=mentioned_symbols,
            error_patterns=error_patterns,
            searchable_text=searchable_text,
            code_blocks=code_blocks[:3],
            stack_traces=stack_traces[:3],
        )

    def _clean_text(self, text: str, code_blocks: Optional[list[str]] = None) -> str:
        if not text:
            return ""

        code_blocks = code_blocks or []
        cleaned = text
        cleaned = self.CODE_BLOCK_RE.sub("\n", cleaned)
        cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
        cleaned = re.sub(r"<!--[\s\S]*?-->", "", cleaned)
        cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
        cleaned = re.sub(r"#+", "#", cleaned)

        lines = []
        for line in cleaned.split("\n"):
            line = line.strip()
            if line and not line.startswith(">"):
                lines.append(line)

        if code_blocks:
            lines.append("Technical snippets:")
            for block in code_blocks[:2]:
                excerpt = self._sanitize_code_block(block)
                if excerpt:
                    lines.append(excerpt)

        return "\n".join(lines)

    def _extract_code_blocks(self, text: str) -> list[str]:
        blocks = []
        for match in self.CODE_BLOCK_RE.finditer(text or ""):
            excerpt = self._sanitize_code_block(match.group(1))
            if excerpt:
                blocks.append(excerpt)
        return blocks[:4]

    def _sanitize_code_block(self, block: str) -> str:
        lines = [line.rstrip() for line in block.splitlines() if line.strip()]
        if not lines:
            return ""
        return "\n".join(lines[:12])[:600]

    def _extract_stack_traces(self, text: str) -> list[str]:
        traces = []
        for line in (text or "").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("Traceback") or stripped.startswith("File ") or "Error:" in stripped:
                traces.append(stripped)
            elif re.search(r"\bat\b .*:\d+", stripped):
                traces.append(stripped)
        return traces[:6]

    def _classify_issue_type(self, title: str, body: str) -> IssueType:
        full_text = (title + " " + body).lower()

        best_match = IssueType.UNKNOWN
        best_score = 0
        for issue_type, keywords in self.ISSUE_TYPE_KEYWORDS.items():
            score = sum(1 for keyword in keywords if keyword in full_text)
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
                normalized = path.strip("`")
                if normalized not in seen and len(normalized) > 3:
                    seen.add(normalized)
                    files.append(ExtractedFile(path=normalized, is_exact=True))

        return files

    def _extract_symbol_mentions(self, text: str) -> list[ExtractedSymbol]:
        symbols = []
        seen = set()

        for pattern in self.FUNCTION_PATTERNS + self.SYMBOL_PATTERNS:
            for match in re.finditer(pattern, text):
                name = match.group(1)
                if name and name not in seen and len(name) > 2:
                    seen.add(name)
                    context_start = max(0, match.start() - 30)
                    context = text[context_start:match.start() + 50]
                    symbols.append(ExtractedSymbol(name=name, context=context.strip()))

        return symbols[:20]

    def _extract_error_patterns(self, text: str) -> list[ExtractedError]:
        errors = []
        for pattern in self.STACK_TRACE_PATTERNS:
            for match in re.finditer(pattern, text or ""):
                groups = [str(group) for group in match.groups() if group]
                if not groups:
                    continue
                file_hint = groups[0] if "/" in groups[0] or "." in groups[0] else None
                line_hint = None
                for group in groups[1:]:
                    if group.isdigit():
                        line_hint = int(group)
                        break
                errors.append(
                    ExtractedError(
                        pattern=":".join(groups),
                        file_hint=file_hint,
                        line_hint=line_hint,
                    )
                )
        return errors[:5]

    def _build_searchable_text(
        self,
        title: str,
        body: str,
        files: list[ExtractedFile],
        symbols: list[ExtractedSymbol],
        code_blocks: list[str],
        stack_traces: list[str],
        errors: list[ExtractedError],
    ) -> str:
        parts = [title]
        if body:
            parts.append(body[:1500])

        parts.extend(file_ref.path for file_ref in files[:8])
        parts.extend(symbol.name for symbol in symbols[:12])
        parts.extend(error.pattern for error in errors[:4])
        parts.extend(block.replace("\n", " ")[:240] for block in code_blocks[:2])
        parts.extend(trace[:180] for trace in stack_traces[:3])

        return " | ".join(part for part in parts if part)


__all__ = [
    "IssueType",
    "ExtractedFile",
    "ExtractedSymbol",
    "ExtractedError",
    "IssueCommentContext",
    "ProcessedIssue",
    "IssuePreprocessor",
]
