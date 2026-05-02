from __future__ import annotations

import json
import unittest

from src.analyzer.ai_scorer import AIScorer, build_ai_prompt, build_ai_request, parse_ai_response, pack_context_units
from src.analyzer.llm_provider import LLMRequest, MockProvider
from src.analyzer.preprocessor import ExtractedFile, IssueCommentContext, IssueType, ProcessedIssue
from src.analyzer.retriever import RetrievalResult, RetrievedUnit
from src.analyzer.scorer import DifficultyScore, ScoringResult


def make_valid_response(**overrides) -> str:
    payload = {
        "difficulty": "easy",
        "confidence": 0.88,
        "core_problem": "The issue likely lives in issue reference parsing and needs a regression test.",
        "strategic_guidance": [
            "Reproduce the failing issue number parsing path before editing code.",
            "Trace parse_issue_ref through the owner/repo fallback logic.",
            "Compare the failing path with the URL and owner/repo#num parsing branches.",
            "Be careful to preserve existing accepted issue reference formats.",
        ],
        "suggested_approach": [
            "Add a failing test for plain issue numbers.",
            "Update parse_issue_ref to support the missing case.",
            "Run the focused client tests and verify no existing formats regress.",
        ],
        "positive_signals": ["A focused parser function is already identified."],
        "warning_signals": ["Parsing changes can silently break accepted reference formats."],
        "is_good_first_issue": True,
        "files_to_focus": ["src/github/client.py", "tests/test_client.py"],
        "why_these_files": [
            "src/github/client.py contains parse_issue_ref, which is explicitly named in the issue.",
            "tests/test_client.py is the fastest place to add a regression case.",
        ],
        "uncertainty_notes": [],
    }
    payload.update(overrides)
    return json.dumps(payload)


class TestBuildAIPrompt(unittest.TestCase):
    def make_retrieval(self):
        issue = ProcessedIssue(
            title="Fix bug in parser",
            body="The parser crashes when given empty input.",
            issue_type=IssueType.BUG,
            mentioned_files=[ExtractedFile(path="src/parser.py")],
            searchable_text="parser crash empty",
            comments=[
                IssueCommentContext(
                    body="Please add a regression test.",
                    author="maintainer",
                    is_maintainer=True,
                    reactions=4,
                )
            ],
            code_blocks=['raise RuntimeError("boom")'],
            stack_traces=['File "src/parser.py", line 12, in parse'],
        )
        retrieval = RetrievalResult(
            issue=issue,
            units=[
                RetrievedUnit(
                    id="u1",
                    path="src/parser.py",
                    name="parse",
                    unit_type="function",
                    language="python",
                    start_line=1,
                    end_line=10,
                    signature="def parse(x):",
                    docstring="Parse input",
                    code="def parse(x):\n    return x",
                    match_reasons=["explicit file mention", "exact symbol mention"],
                )
            ],
        )
        return retrieval

    def test_build_prompt_includes_issue_info_and_evidence(self):
        prompt = build_ai_prompt(self.make_retrieval())
        self.assertIn("Fix bug in parser", prompt)
        self.assertIn("Type: BUG", prompt)
        self.assertIn("Issue Discussion & Comments", prompt)
        self.assertIn("Why selected:", prompt)
        self.assertIn('raise RuntimeError("boom")', prompt)

    def test_build_request_uses_json_mode(self):
        request = build_ai_request(self.make_retrieval(), temperature=0.2, max_tokens=900, context_unit_budget=4)
        self.assertEqual(request.temperature, 0.2)
        self.assertEqual(request.max_tokens, 900)
        self.assertEqual(request.response_format, {"type": "json_object"})
        self.assertIn("Return exactly one JSON object", request.system)

    def test_context_packer_labels_unit_reasons(self):
        packed = pack_context_units(self.make_retrieval(), context_unit_budget=3)
        self.assertEqual(len(packed), 1)
        self.assertIn("explicit file mention", packed[0].reason)


class TestParseAIResponse(unittest.TestCase):
    def test_parses_valid_json(self):
        result = parse_ai_response(make_valid_response())
        self.assertEqual(result["difficulty"], "easy")
        self.assertEqual(result["files_to_focus"][0], "src/github/client.py")

    def test_extracts_json_from_text(self):
        response = f"Here is the analysis:\n{make_valid_response()}\nThanks!"
        result = parse_ai_response(response)
        self.assertEqual(result["difficulty"], "easy")

    def test_rejects_schema_drift(self):
        with self.assertRaises(ValueError):
            parse_ai_response(
                json.dumps(
                    {
                        "difficulty": "easy",
                        "confidence": 0.9,
                        "core_problem": "x",
                        "strategic_guidance": ["a", "b", "c", "d"],
                        "suggested_approach": ["1", "2", "3"],
                        "positive_signals": [],
                        "warning_signals": [],
                        "is_good_first_issue": True,
                        "files_to_focus": [],
                        "why_these_files": [],
                        "uncertainty_notes": [],
                        "extra_field": "not allowed",
                    }
                )
            )

    def test_raises_on_invalid_json(self):
        with self.assertRaises(ValueError):
            parse_ai_response("not valid json at all")


class TestAIScorerBasic(unittest.TestCase):
    def test_ai_scorer_returns_richer_fields(self):
        retrieval = RetrievalResult(
            issue=ProcessedIssue(
                title="Fix issue parsing",
                body="Fix plain number parsing",
                issue_type=IssueType.BUG,
                mentioned_files=[ExtractedFile(path="src/github/client.py")],
                searchable_text="parse issue references",
            ),
            units=[
                RetrievedUnit(
                    id="u1",
                    path="src/github/client.py",
                    name="parse_issue_ref",
                    unit_type="function",
                    language="python",
                    start_line=1,
                    end_line=20,
                    signature="def parse_issue_ref(ref):",
                    docstring="Parse issue references",
                    code="def parse_issue_ref(ref):\n    return ref\n",
                    match_reasons=["explicit file mention"],
                )
            ],
        )

        heuristic_result = ScoringResult(
            issue_title="Fix issue parsing",
            overall_difficulty=DifficultyScore(raw_score=0.3, difficulty="easy", confidence=0.8),
            positive_signals=["Has a focused entry point"],
            warning_signals=["Needs regression coverage"],
            suggested_approach=["1. Add a failing test"],
            why_these_files=["src/github/client.py is the parsing entry point"],
            uncertainty_notes=["No stack trace was provided."],
        )

        class FallbackScorer:
            def score(self, retrieval):
                return heuristic_result

        scorer = AIScorer(
            provider=MockProvider(make_valid_response()),
            fallback_scorer=FallbackScorer(),
            context_unit_budget=4,
        )
        result = scorer.score(retrieval)

        self.assertEqual(result.overall_difficulty.difficulty, "easy")
        self.assertTrue(result.why_these_files)
        self.assertEqual(result.uncertainty_notes, [])

    def test_ai_scorer_signature_changes_with_settings(self):
        scorer_a = AIScorer(provider=MockProvider(make_valid_response()), temperature=0.1, max_tokens=800, context_unit_budget=6)
        scorer_b = AIScorer(provider=MockProvider(make_valid_response()), temperature=0.2, max_tokens=800, context_unit_budget=6)
        self.assertNotEqual(scorer_a.get_analysis_signature(), scorer_b.get_analysis_signature())


if __name__ == "__main__":
    unittest.main()
