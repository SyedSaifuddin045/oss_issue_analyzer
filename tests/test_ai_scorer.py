from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock

from src.analyzer.ai_scorer import (
    AIScorer,
    build_ai_prompt,
    parse_ai_response,
    AIScoringError,
)
from src.analyzer.retriever import RetrievalResult, RetrievedUnit
from src.analyzer.preprocessor import ProcessedIssue, IssueType, ExtractedFile
from src.analyzer.scorer import ScoringResult, DifficultyScore


class TestBuildAIPrompt(unittest.TestCase):
    def test_build_prompt_includes_issue_info(self):
        issue = ProcessedIssue(
            title="Fix bug in parser",
            body="The parser crashes when given empty input",
            issue_type=IssueType.BUG,
            mentioned_files=[ExtractedFile(path="src/parser.py")],
            mentioned_symbols=[],
            searchable_text="parser crash empty",
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
                )
            ],
        )
        
        prompt = build_ai_prompt(retrieval)
        
        self.assertIn("Fix bug in parser", prompt)
        self.assertIn("BUG", prompt)
        self.assertIn("src/parser.py", prompt)
        self.assertIn("parse", prompt)

    def test_build_prompt_includes_heuristic_context(self):
        issue = ProcessedIssue(
            title="Test issue",
            body="Test body",
            issue_type=IssueType.FEATURE,
            mentioned_files=[],
            mentioned_symbols=[],
            searchable_text="test",
        )
        
        heuristic_result = ScoringResult(
            issue_title="Test issue",
            overall_difficulty=DifficultyScore(
                raw_score=0.3,
                difficulty="easy",
                confidence=0.8,
            ),
            positive_signals=["Has test files"],
            warning_signals=["May affect production"],
            suggested_approach=["Start in tests/"],
        )
        
        retrieval = RetrievalResult(issue=issue, units=[])
        prompt = build_ai_prompt(retrieval, heuristic_result)
        
        self.assertIn("Heuristic Analysis", prompt)
        self.assertIn("easy", prompt)
        self.assertIn("Has test files", prompt)

    def test_build_prompt_includes_comments(self):
        issue = ProcessedIssue(
            title="Feature request",
            body="Add new feature",
            issue_type=IssueType.FEATURE,
            mentioned_files=[],
            mentioned_symbols=[],
            searchable_text="feature",
            comments=[
                "Please follow the CONTRIBUTING.md guidelines when submitting PRs",
                "Great idea! Please also add tests.",
            ],
        )
        
        retrieval = RetrievalResult(issue=issue, units=[])
        prompt = build_ai_prompt(retrieval)
        
        self.assertIn("Issue Discussion & Comments", prompt)
        self.assertIn("CONTRIBUTING.md", prompt)
        self.assertIn("add tests", prompt)


class TestParseAIResponse(unittest.TestCase):
    def test_parses_valid_json(self):
        response = json.dumps({
            "difficulty": "easy",
            "confidence": 0.9,
            "reasoning": "Simple fix",
            "suggested_approach": ["Step 1", "Step 2"],
            "positive_signals": ["Good test coverage"],
            "warning_signals": [],
            "is_good_first_issue": True,
            "files_to_focus": ["src/main.py"],
        })
        
        result = parse_ai_response(response)
        
        self.assertEqual(result["difficulty"], "easy")
        self.assertEqual(result["confidence"], 0.9)
        self.assertEqual(result["suggested_approach"], ["Step 1", "Step 2"])
        self.assertTrue(result["is_good_first_issue"])

    def test_handles_missing_fields(self):
        response = '{"difficulty": "medium"}'
        
        result = parse_ai_response(response)
        
        self.assertEqual(result["difficulty"], "medium")
        self.assertEqual(result["confidence"], 0.5)
        self.assertEqual(result["suggested_approach"], [])

    def test_handles_invalid_difficulty(self):
        response = '{"difficulty": "impossible"}'
        
        result = parse_ai_response(response)
        
        self.assertEqual(result["difficulty"], "medium")

    def test_extracts_json_from_text(self):
        response = '''Here is my analysis:
{
    "difficulty": "hard",
    "confidence": 0.7
}
Hope this helps!'''
        
        result = parse_ai_response(response)
        
        self.assertEqual(result["difficulty"], "hard")
        self.assertEqual(result["confidence"], 0.7)

    def test_raises_on_invalid_json(self):
        response = "not valid json at all"
        
        with self.assertRaises(ValueError):
            parse_ai_response(response)


class TestAIScorerBasic(unittest.TestCase):
    def test_parse_ai_response_with_various_difficulties(self):
        for difficulty in ["easy", "medium", "hard"]:
            response = json.dumps({"difficulty": difficulty, "confidence": 0.8})
            result = parse_ai_response(response)
            self.assertEqual(result["difficulty"], difficulty)

    def test_default_values_for_optional_fields(self):
        response = json.dumps({
            "difficulty": "easy",
        })
        result = parse_ai_response(response)
        
        self.assertIn("reasoning", result)
        self.assertIn("positive_signals", result)
        self.assertIn("warning_signals", result)
        self.assertIn("is_good_first_issue", result)
        self.assertIn("files_to_focus", result)


if __name__ == "__main__":
    unittest.main()