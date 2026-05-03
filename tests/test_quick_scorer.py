from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from src.analyzer.preprocessor import ProcessedIssue, IssueType
from src.analyzer.scorer import DifficultyScore, DifficultyLabel
from src.analyzer.retriever import RetrievalResult, RetrievedUnit
from src.analyzer.quick_scorer import QuickHeuristicScorer
from src.indexer.dependencies import DependencyProfile


class TestQuickHeuristicScorer(unittest.TestCase):
    def setUp(self):
        self.scorer = QuickHeuristicScorer()

    def test_easy_issue_with_good_first_label(self):
        issue = ProcessedIssue(
            title="Fix typo in README",
            body="Simple fix needed",
            issue_type=IssueType.DOCS,
        )
        result = self.scorer.score(issue, labels=["good first issue"])
        
        self.assertEqual(result.difficulty, DifficultyLabel.EASY)
        self.assertLess(result.raw_score, 0.35)

    def test_hard_issue_with_refactor_label(self):
        issue = ProcessedIssue(
            title="Refactor entire database layer",
            body="This is a massive change that affects multiple components " * 20,  # Make body long
            issue_type=IssueType.REFACTOR,
        )
        result = self.scorer.score(issue, labels=["enhancement"])
        
        self.assertEqual(result.difficulty, DifficultyLabel.HARD)

    def test_bug_with_error_patterns(self):
        issue = ProcessedIssue(
            title="Fix crash in parser",
            body="The parser crashes",
            issue_type=IssueType.BUG,
            error_patterns=[{"pattern": "KeyError"}],
        )
        result = self.scorer.score(issue, labels=[])
        
        self.assertIn(result.difficulty, [DifficultyLabel.EASY, DifficultyLabel.MEDIUM])

    def test_metadata_only_low_confidence(self):
        issue = ProcessedIssue(
            title="Some issue",
            body="Body text",
            issue_type=IssueType.UNKNOWN,
        )
        result = self.scorer.score(issue, retrieval=None, labels=[])
        
        self.assertLess(result.confidence, 0.6)

    def test_with_code_retrieval_higher_confidence(self):
        issue = ProcessedIssue(
            title="Fix function",
            body="Fix this function",
            issue_type=IssueType.BUG,
        )
        retrieval = RetrievalResult(
            issue=issue,
            units=[
                RetrievedUnit(
                    id="u1",
                    path="src/main.py",
                    name="fix_me",
                    unit_type="function",
                    language="python",
                    start_line=1,
                    end_line=10,
                    signature="def fix_me():",
                    docstring="Fix this",
                    code="def fix_me():\n    return 1\n",
                )
            ],
        )
        result = self.scorer.score(issue, retrieval=retrieval, labels=[])
        
        self.assertGreaterEqual(result.confidence, 0.6)

    def test_issue_type_docs_is_easy(self):
        issue = ProcessedIssue(
            title="Update documentation",
            body="Please update the docs",
            issue_type=IssueType.DOCS,
        )
        result = self.scorer.score(issue, labels=[])
        
        self.assertEqual(result.difficulty, DifficultyLabel.EASY)

    def test_help_wanted_label(self):
        issue = ProcessedIssue(
            title="Good contribution opportunity",
            body="We need help with this",
            issue_type=IssueType.FEATURE,
        )
        result = self.scorer.score(issue, labels=["help wanted"])
        
        self.assertIn(result.difficulty, [DifficultyLabel.EASY, DifficultyLabel.MEDIUM])

    def test_confidence_without_code_is_low(self):
        issue = ProcessedIssue(
            title="Test",
            body="Test body",
            issue_type=IssueType.BUG,
        )
        result = self.scorer.score(issue, retrieval=None, labels=[])
        self.assertLess(result.confidence, 0.6)

    def test_confidence_with_code_is_medium(self):
        issue = ProcessedIssue(
            title="Test",
            body="Test body",
            issue_type=IssueType.BUG,
        )
        retrieval = RetrievalResult(
            issue=issue,
            units=[RetrievedUnit(
                id="u1", path="test.py", name="test",
                unit_type="function", language="python",
                start_line=1, end_line=5,
                signature="def test():", docstring="",
                code="def test():\n    pass\n",
            )],
        )
        result = self.scorer.score(issue, retrieval=retrieval, labels=[])
        self.assertGreaterEqual(result.confidence, 0.6)

    def test_dependency_profile_adds_baseline_complexity(self):
        issue = ProcessedIssue(
            title="Investigate flaky dependency resolution",
            body="Install occasionally fails on CI",
            issue_type=IssueType.BUG,
        )
        retrieval = RetrievalResult(
            issue=issue,
            units=[],
            dependency_profile=DependencyProfile(
                repo_id="repo-1",
                manifest_count=2,
                ecosystems=["python", "node"],
                manifest_paths=["pyproject.toml", "package.json"],
                direct_dependency_count=90,
                dev_dependency_count=30,
                unpinned_or_broad_range_count=12,
                git_or_path_dependency_count=1,
                override_or_replace_count=1,
                workspace_or_multi_module=True,
                risk_flags=["Large dependency surface area"],
            ),
        )

        result = self.scorer.score(issue, retrieval=retrieval, labels=[])
        self.assertGreater(result.raw_score, 0.4)

    def test_dependency_issue_gets_extra_boost(self):
        issue = ProcessedIssue(
            title="Update pyproject dependency constraints",
            body="Fix install conflicts in pyproject.toml",
            issue_type=IssueType.FEATURE,
        )
        retrieval = RetrievalResult(
            issue=issue,
            units=[RetrievedUnit(
                id="u1", path="pyproject.toml", name="pyproject.toml",
                unit_type="config", language="dependency",
                start_line=1, end_line=12,
                signature=None, docstring=None,
                code="[project]\ndependencies=['httpx>=0.27']\n",
                asset_kind="dependency",
                match_type="explicit",
                is_test=False,
                match_reasons=["explicit file mention"],
            )],
            dependency_profile=DependencyProfile(
                repo_id="repo-1",
                manifest_count=1,
                ecosystems=["python"],
                manifest_paths=["pyproject.toml"],
                direct_dependency_count=25,
                unpinned_or_broad_range_count=10,
            ),
        )

        result = self.scorer.score(issue, retrieval=retrieval, labels=[])
        self.assertIn(result.difficulty, [DifficultyLabel.MEDIUM, DifficultyLabel.HARD])
        self.assertGreater(result.raw_score, 0.45)


if __name__ == "__main__":
    unittest.main()
