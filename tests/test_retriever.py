from __future__ import annotations

import unittest

from src.analyzer.preprocessor import ExtractedFile, ExtractedSymbol, IssueType, ProcessedIssue
from src.analyzer.retriever import HybridRetriever


class FakeEmbedder:
    def embed(self, text: str) -> list[float]:
        assert "parse_issue_ref" in text
        return [0.1, 0.2, 0.3]


class FakeVectorStore:
    def search(self, query: str, query_embedding: list[float], repo_id: str | None = None, unit_type: str | None = None, limit: int = 10) -> list[dict]:
        return [
            {
                "id": "semantic-function",
                "path": "src/github/client.py",
                "name": "parse_issue_ref",
                "unit_type": "function",
                "language": "python",
                "start_line": 10,
                "end_line": 20,
                "signature": "def parse_issue_ref(ref, repo_hint=None):",
                "docstring": "Parse GitHub issue references.",
                "code": "def parse_issue_ref(...): pass",
                "asset_kind": "code",
                "_score": 0.8,
            },
            {
                "id": "semantic-test",
                "path": "tests/test_client.py",
                "name": "test_parse_issue_ref",
                "unit_type": "function",
                "language": "python",
                "start_line": 1,
                "end_line": 8,
                "signature": "def test_parse_issue_ref():",
                "docstring": "Covers issue parsing.",
                "code": "def test_parse_issue_ref(): pass",
                "asset_kind": "code",
                "_score": 0.62,
            },
        ]

    def search_by_text(self, query: str, repo_id: str | None = None, unit_type: str | None = None, limit: int = 10) -> list[dict]:
        if query == "parse_issue_ref":
            return [
                {
                    "id": "semantic-function",
                    "path": "src/github/client.py",
                    "name": "parse_issue_ref",
                    "unit_type": "function",
                    "language": "python",
                    "start_line": 10,
                    "end_line": 20,
                    "signature": "def parse_issue_ref(ref, repo_hint=None):",
                    "docstring": "Parse GitHub issue references.",
                    "code": "def parse_issue_ref(...): pass",
                    "asset_kind": "code",
                },
                {
                    "id": "client-helper",
                    "path": "src/github/client.py",
                    "name": "_parse_repo_hint",
                    "unit_type": "function",
                    "language": "python",
                    "start_line": 30,
                    "end_line": 36,
                    "signature": "def _parse_repo_hint(repo_hint):",
                    "docstring": "Parse owner/repo values.",
                    "code": "def _parse_repo_hint(...): pass",
                    "asset_kind": "code",
                },
            ]
        if query == "src/github/client.py":
            return [
                {
                    "id": "file-entry",
                    "path": "src/github/client.py",
                    "name": None,
                    "unit_type": "file",
                    "language": "python",
                    "start_line": 1,
                    "end_line": 80,
                    "signature": None,
                    "docstring": None,
                    "code": "file contents",
                    "asset_kind": "code",
                }
            ]
        return []


class RetrieverTests(unittest.TestCase):
    def test_hybrid_retriever_preserves_multiple_units_from_same_file(self) -> None:
        retriever = HybridRetriever(embedder=FakeEmbedder())
        retriever._vector_store = FakeVectorStore()

        issue = ProcessedIssue(
            title="Fix parsing plain issue numbers",
            body="`parse_issue_ref` fails for issue 42 in src/github/client.py",
            issue_type=IssueType.BUG,
            mentioned_files=[ExtractedFile(path="src/github/client.py")],
            mentioned_symbols=[ExtractedSymbol(name="parse_issue_ref")],
            searchable_text="Fix parsing plain issue numbers parse_issue_ref src/github/client.py",
        )

        result = retriever.search(issue, repo_id="repo-1", limit=5)

        self.assertEqual(result.search_stats["selected_count"], len(result.units))
        self.assertGreaterEqual(len(result.units), 2)
        self.assertEqual(result.units[0].name, "parse_issue_ref")
        self.assertTrue(any(unit.path == "tests/test_client.py" for unit in result.units))

    def test_hybrid_retriever_boosts_explicit_paths_and_exact_symbols(self) -> None:
        retriever = HybridRetriever(embedder=FakeEmbedder())
        retriever._vector_store = FakeVectorStore()

        issue = ProcessedIssue(
            title="Fix parsing plain issue numbers",
            body="`parse_issue_ref` fails for issue 42 in src/github/client.py",
            issue_type=IssueType.BUG,
            mentioned_files=[ExtractedFile(path="src/github/client.py")],
            mentioned_symbols=[ExtractedSymbol(name="parse_issue_ref")],
            searchable_text="Fix parsing plain issue numbers parse_issue_ref src/github/client.py",
        )

        result = retriever.search(issue, repo_id="repo-1", limit=5)
        top_unit = result.units[0]

        self.assertIn("exact symbol mention", top_unit.match_reasons)
        self.assertIn("explicit file mention", top_unit.match_reasons)
        self.assertGreater(top_unit.score, 0.5)

    def test_hybrid_retriever_downranks_docs_without_docs_signal(self) -> None:
        class DocsVectorStore(FakeVectorStore):
            def search(self, query: str, query_embedding: list[float], repo_id: str | None = None, unit_type: str | None = None, limit: int = 10) -> list[dict]:
                return [
                    {
                        "id": "docs-file",
                        "path": "README.md",
                        "name": "README.md",
                        "unit_type": "document",
                        "language": "text",
                        "start_line": 1,
                        "end_line": 20,
                        "signature": None,
                        "docstring": None,
                        "code": "# README",
                        "asset_kind": "docs",
                        "_score": 0.8,
                    }
                ]

            def search_by_text(self, query: str, repo_id: str | None = None, unit_type: str | None = None, limit: int = 10) -> list[dict]:
                return []

        retriever = HybridRetriever(embedder=FakeEmbedder())
        retriever._vector_store = DocsVectorStore()

        issue = ProcessedIssue(
            title="Fix parsing plain issue numbers",
            body="`parse_issue_ref` fails when parsing issue 42",
            issue_type=IssueType.BUG,
            mentioned_symbols=[ExtractedSymbol(name="parse_issue_ref")],
            searchable_text="Fix parsing plain issue numbers parse_issue_ref",
        )

        result = retriever.search(issue, repo_id="repo-1", limit=5)
        self.assertEqual(result.units[0].asset_kind, "docs")
        self.assertLess(result.units[0].score, 0.5)


if __name__ == "__main__":
    unittest.main()
