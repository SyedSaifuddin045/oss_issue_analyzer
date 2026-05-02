from __future__ import annotations

import unittest

from src.analyzer.preprocessor import (
    ExtractedFile,
    ExtractedSymbol,
    IssueCommentContext,
    IssuePreprocessor,
    IssueType,
    ProcessedIssue,
)
from src.analyzer.retriever import RetrievalResult, RetrievedUnit
from src.analyzer.scorer import HeuristicScorer


class PreprocessorAndScoringTests(unittest.TestCase):
    def test_issue_preprocessor_preserves_technical_evidence(self) -> None:
        preprocessor = IssuePreprocessor()
        processed = preprocessor.process(
            "Bug: fix parser crash in `parse_issue_ref`",
            """
            The parser fails in `src/github/client.py`.

            ```python
            raise RuntimeError("boom")
            ```

            Traceback:
            File "src/github/client.py", line 12, in parse_issue_ref
            """,
        )

        self.assertIs(processed.issue_type, IssueType.BUG)
        self.assertEqual(processed.mentioned_files[0].path, "src/github/client.py")
        self.assertTrue(any(symbol.name == "parse_issue_ref" for symbol in processed.mentioned_symbols))
        self.assertTrue(processed.error_patterns)
        self.assertTrue(processed.code_blocks)
        self.assertIn("RuntimeError", processed.searchable_text)

    def test_heuristic_scorer_flags_easy_well_scoped_bug(self) -> None:
        scorer = HeuristicScorer()
        retrieval = RetrievalResult(
            issue=ProcessedIssue(
                title="Fix parser crash",
                body="Crash when parsing issue numbers",
                issue_type=IssueType.BUG,
                mentioned_files=[ExtractedFile(path="src/github/client.py")],
                mentioned_symbols=[ExtractedSymbol(name="parse_issue_ref")],
                searchable_text="Fix parser crash parse_issue_ref src/github/client.py",
                stack_traces=['File "src/github/client.py", line 12'],
                comments=[IssueCommentContext(body="Please add a regression test", author="maintainer", is_maintainer=True)],
            ),
            units=[
                RetrievedUnit(
                    id="u1",
                    path="tests/test_client.py",
                    name="test_parse_issue_ref",
                    unit_type="function",
                    language="python",
                    start_line=1,
                    end_line=8,
                    signature="def test_parse_issue_ref():",
                    docstring="covers plain issue numbers",
                    code="def test_parse_issue_ref():\n    assert True\n",
                    is_test=True,
                    match_reasons=["nearby test coverage"],
                )
            ],
        )

        result = scorer.score(retrieval)

        self.assertEqual(result.overall_difficulty.difficulty, "easy")
        self.assertTrue(result.is_good_first_issue)
        self.assertIn("Bug report with clear scope", result.positive_signals)
        self.assertTrue(any("Start in tests/test_client.py" in suggestion for suggestion in result.suggested_approach))
        self.assertTrue(result.why_these_files)

    def test_heuristic_scorer_formats_non_code_suggestions(self) -> None:
        scorer = HeuristicScorer()
        retrieval = RetrievalResult(
            issue=ProcessedIssue(
                title="Update CI config for uv",
                body="The workflow should install uv before tests.",
                issue_type=IssueType.FEATURE,
                mentioned_files=[ExtractedFile(path=".github/workflows/ci.yml")],
                searchable_text="Update CI config .github/workflows/ci.yml uv",
            ),
            units=[
                RetrievedUnit(
                    id="u1",
                    path=".github/workflows/ci.yml",
                    name=".github/workflows/ci.yml",
                    unit_type="config",
                    language="text",
                    start_line=1,
                    end_line=10,
                    signature=None,
                    docstring=None,
                    code="name: CI\njobs:\n  test:\n",
                    asset_kind="workflow",
                    match_type="explicit",
                    match_reasons=["explicit file mention"],
                ),
                RetrievedUnit(
                    id="u2",
                    path="pyproject.toml",
                    name="pyproject.toml",
                    unit_type="config",
                    language="text",
                    start_line=1,
                    end_line=8,
                    signature=None,
                    docstring=None,
                    code="[project]\nname='demo'\n",
                    asset_kind="config",
                    match_type="keyword",
                    match_reasons=["keyword match"],
                ),
            ],
        )

        result = scorer.score(retrieval)

        self.assertTrue(any("workflow changes" in suggestion for suggestion in result.suggested_approach))
        self.assertTrue(any("related configuration" in suggestion for suggestion in result.suggested_approach))
        self.assertNotIn("Clear interface", result.positive_signals)


if __name__ == "__main__":
    unittest.main()
