from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.analyzer.ai_scorer import build_ai_prompt, parse_ai_response
from src.analyzer.preprocessor import ExtractedFile, IssueCommentContext, IssueType, ProcessedIssue
from src.analyzer.retriever import RetrievalResult, RetrievedUnit


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "issue_eval_fixture.json"


class TestAIEvaluationFixture(unittest.TestCase):
    def test_fixture_covers_prompt_and_schema(self):
        with open(FIXTURE_PATH, encoding="utf-8") as handle:
            fixture = json.load(handle)

        issue = ProcessedIssue(
            title=fixture["issue"]["title"],
            body=fixture["issue"]["body"],
            issue_type=IssueType(fixture["issue"]["issue_type"]),
            mentioned_files=[ExtractedFile(path=path) for path in fixture["issue"]["mentioned_files"]],
            searchable_text=fixture["issue"]["searchable_text"],
            comments=[
                IssueCommentContext(
                    body=comment["body"],
                    author=comment["author"],
                    is_maintainer=comment["is_maintainer"],
                    reactions=comment["reactions"],
                )
                for comment in fixture["issue"]["comments"]
            ],
            code_blocks=fixture["issue"]["code_blocks"],
            stack_traces=fixture["issue"]["stack_traces"],
        )
        retrieval = RetrievalResult(
            issue=issue,
            units=[
                RetrievedUnit(**unit)
                for unit in fixture["retrieval_units"]
            ],
        )

        prompt = build_ai_prompt(retrieval, context_unit_budget=4)
        self.assertIn("Ranked Code Context", prompt)
        self.assertIn("Issue Discussion & Comments", prompt)
        self.assertIn("Why selected:", prompt)

        parsed = parse_ai_response(json.dumps(fixture["expected_response"]))
        self.assertIn("why_these_files", parsed)
        self.assertIn("uncertainty_notes", parsed)


if __name__ == "__main__":
    unittest.main()
