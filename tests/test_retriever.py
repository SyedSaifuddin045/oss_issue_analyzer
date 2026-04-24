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
                "id": "semantic-file",
                "path": "src/github/client.py",
                "name": "parse_issue_ref",
                "unit_type": "function",
                "language": "python",
                "start_line": 10,
                "end_line": 20,
                "signature": "def parse_issue_ref(ref, repo_hint=None):",
                "docstring": "Parse GitHub issue references.",
                "code": "def parse_issue_ref(...): pass",
                "_score": 0.8,
            }
        ]

    def search_by_text(self, query: str, repo_id: str | None = None, unit_type: str | None = None, limit: int = 10) -> list[dict]:
        if query == "parse_issue_ref":
            return [
                {
                    "id": "semantic-file",
                    "path": "src/github/client.py",
                    "name": "parse_issue_ref",
                    "unit_type": "function",
                    "language": "python",
                    "start_line": 10,
                    "end_line": 20,
                    "signature": "def parse_issue_ref(ref, repo_hint=None):",
                    "docstring": "Parse GitHub issue references.",
                    "code": "def parse_issue_ref(...): pass",
                }
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
                }
            ]
        return []


class RetrieverTests(unittest.TestCase):
    def test_hybrid_retriever_combines_semantic_keyword_and_explicit_results(self) -> None:
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

        self.assertEqual(
            result.search_stats,
            {"semantic_count": 1, "keyword_count": 1, "explicit_count": 1},
        )
        self.assertEqual([unit.path for unit in result.units], ["src/github/client.py"])
        self.assertGreater(result.units[0].score, 0.0)


if __name__ == "__main__":
    unittest.main()
