from __future__ import annotations

import unittest

from src.analyzer.preprocessor import (
    ExtractedFile,
    ExtractedSymbol,
    IssuePreprocessor,
    IssueType,
    ProcessedIssue,
)
from src.analyzer.retriever import RetrievalResult, RetrievedUnit
from src.analyzer.scorer import HeuristicScorer


class PreprocessorAndScoringTests(unittest.TestCase):
    def test_issue_preprocessor_cleans_markup_and_extracts_signals(self) -> None:
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
        self.assertNotIn("boom", processed.searchable_text)

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
                )
            ],
        )

        result = scorer.score(retrieval)

        self.assertEqual(result.overall_difficulty.difficulty, "easy")
        self.assertTrue(result.is_good_first_issue)
        self.assertIn("Bug report with clear scope", result.positive_signals)
        self.assertTrue(
            any("Start in tests/test_client.py" in suggestion for suggestion in result.suggested_approach)
        )


if __name__ == "__main__":
    unittest.main()
