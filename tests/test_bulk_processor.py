from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch, PropertyMock
from concurrent.futures import ThreadPoolExecutor

from src.github.client import GitHubIssue
from src.analyzer.quick_scorer import QuickHeuristicScorer
from src.analyzer.preprocessor import IssuePreprocessor, IssueType
from src.analyzer.retriever import HybridRetriever, RetrievalResult, RetrievedUnit


class TestBulkProcessor(unittest.TestCase):
    def test_processor_handles_empty_list(self):
        from src.analyzer.bulk_processor import BulkProcessor
        processor = BulkProcessor(db_path="/nonexistent", repo_id="test123")
        result = processor.process_issues([], limit=0)
        self.assertEqual(result, [])

    @patch("src.analyzer.bulk_processor.HybridRetriever")
    @patch("src.analyzer.bulk_processor.IssuePreprocessor")
    def test_process_single_issue(self, mock_preprocessor_class, mock_retriever_class):
        from src.analyzer.bulk_processor import _process_single_issue

        mock_preprocessor = MagicMock()
        mock_preprocessor.process.return_value = MagicMock(
            issue_type=IssueType.BUG,
            labels=[],
            error_patterns=[],
        )
        mock_preprocessor_class.return_value = mock_preprocessor

        mock_retriever = MagicMock()
        mock_retriever.search.return_value = RetrievalResult(
            issue=mock_preprocessor.process.return_value,
            units=[],
        )
        mock_retriever_class.return_value = mock_retriever

        worker_state = (mock_preprocessor, mock_retriever, QuickHeuristicScorer())

        issue = GitHubIssue(
            number=123,
            title="Fix bug",
            body="Bug description",
            state="open",
            html_url="https://...",
            user_login="user1",
            created_at="2026-01-01",
            labels=[],
        )

        with patch("src.analyzer.quick_scorer.QuickHeuristicScorer.score") as mock_score:
            mock_score.return_value = MagicMock(
                difficulty=MagicMock(value="easy"),
                confidence=0.8,
                raw_score=0.3,
            )
            result = _process_single_issue(issue, worker_state)

        self.assertEqual(result["number"], 123)
        self.assertEqual(result["title"], "Fix bug")
        self.assertEqual(result["difficulty"], "easy")

    def test_process_issues_with_limit(self):
        from src.analyzer.bulk_processor import BulkProcessor

        issues = [
            GitHubIssue(
                number=i,
                title=f"Issue {i}",
                body=f"Body {i}",
                state="open",
                html_url=f"https://.../{i}",
                user_login="user",
                created_at="2026-01-01",
                labels=[],
            )
            for i in range(10)
        ]

        processor = BulkProcessor(db_path="/nonexistent", repo_id="test123")
        with patch("src.analyzer.bulk_processor._make_worker_state") as mock_state:
            mock_state.return_value = (MagicMock(), MagicMock(), MagicMock())
            with patch("src.analyzer.bulk_processor._process_single_issue") as mock_process:
                mock_process.side_effect = [
                    {"number": issue.number, "title": issue.title, "difficulty": "easy", "confidence": 0.8, "quick_score": 0.2}
                    for issue in issues[:5]
                ]
                result = processor.process_issues(issues, limit=5)

        self.assertEqual(len(result), 5)

    def test_results_sorted_by_score(self):
        from src.analyzer.bulk_processor import BulkProcessor

        issues = [
            GitHubIssue(
                number=1,
                title="Easy issue",
                body="Simple",
                state="open",
                html_url="https://...",
                user_login="user",
                created_at="2026-01-01",
                labels=["good first issue"],
            ),
            GitHubIssue(
                number=2,
                title="Hard issue",
                body="Very complex " * 200,
                state="open",
                html_url="https://...",
                user_login="user",
                created_at="2026-01-01",
                labels=["enhancement"],
            ),
        ]

        processor = BulkProcessor(db_path="/nonexistent", repo_id="test123")

        with patch("src.analyzer.bulk_processor._make_worker_state") as mock_state:
            mock_state.return_value = (MagicMock(), MagicMock(), MagicMock())

            with patch("src.analyzer.bulk_processor._process_single_issue") as mock_process:
                mock_process.side_effect = [
                    {"number": 1, "title": "Easy", "difficulty": "easy", "confidence": 0.8, "quick_score": 0.2},
                    {"number": 2, "title": "Hard", "difficulty": "hard", "confidence": 0.7, "quick_score": 0.8},
                ]
                result = processor.process_issues(issues, limit=0)

        self.assertEqual(result[0]["number"], 1)  # Easy first
        self.assertEqual(result[1]["number"], 2)  # Hard second

    def test_max_workers_auto_detect(self):
        from src.analyzer.bulk_processor import BulkProcessor
        import os

        with patch("os.cpu_count", return_value=4):
            processor = BulkProcessor(db_path="/nonexistent", repo_id="test123")
            self.assertLessEqual(processor.max_workers, 4)

        with patch("os.cpu_count", return_value=16):
            processor = BulkProcessor(db_path="/nonexistent", repo_id="test123")
            self.assertEqual(processor.max_workers, 8)  # Capped at 8

    @patch("src.analyzer.bulk_processor.HybridRetriever")
    def test_make_worker_state_sets_repo_once_for_dependency_context(self, mock_retriever_class):
        from src.analyzer.bulk_processor import _make_worker_state

        mock_retriever = MagicMock()
        mock_retriever_class.return_value = mock_retriever

        _make_worker_state("/tmp/index.lance", "repo-123")

        mock_retriever.set_repo.assert_called_once_with("repo-123")


if __name__ == "__main__":
    unittest.main()
