from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from src.analyzer.scorer import (
    ContributorSignal,
    DifficultyScore,
    DifficultyLabel,
    ScoringResult,
    UnitScore,
)
from src.analyzer.llm_provider import LLMProvider
from src.analyzer.retriever import RetrievalResult, RetrievedUnit


SYSTEM_PROMPT = """You are an expert open source contributor helping analyze GitHub issues for first-time contributors.

Your task is to analyze the issue and provide:
1. A difficulty assessment (easy/medium/hard) with confidence
2. Suggested approach for solving the issue
3. Potential pitfalls and warnings
4. Whether this is a good first issue

Respond in JSON format with the following structure:
{
    "difficulty": "easy|medium|hard",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation",
    "suggested_approach": ["step 1", "step 2", "step 3"],
    "positive_signals": ["signal 1", "signal 2"],
    "warning_signals": ["warning 1", "warning 2"],
    "is_good_first_issue": true|false,
    "files_to_focus": ["file1", "file2"]
}

Be concise but helpful. Focus on practical advice for newcomers."""


def build_ai_prompt(retrieval: RetrievalResult, heuristic_result: Optional[ScoringResult] = None) -> str:
    issue = retrieval.issue
    
    prompt_parts = [
        f"# Issue Analysis Request",
        f"",
        f"## Issue Information",
        f"Title: {issue.title}",
        f"Type: {issue.issue_type}",
        f"",
    ]
    
    if issue.body:
        body_snippet = issue.body[:1500] if len(issue.body) > 1500 else issue.body
        prompt_parts.append(f"Body (truncated):\n{body_snippet}\n")
    
    if issue.error_patterns:
        prompt_parts.append(f"Error patterns: {', '.join(issue.error_patterns[:3])}\n")
    
    prompt_parts.extend([
        f"## Relevant Code Units Retrieved ({len(retrieval.units)} found)",
        f"",
    ])
    
    for i, unit in enumerate(retrieval.units[:8]):
        unit_info = f"### Unit {i+1}: {unit.path}"
        if unit.name:
            unit_info += f" -> {unit.name}"
        unit_info += f" ({unit.unit_type}, {unit.language})"
        
        if unit.signature:
            unit_info += f"\nSignature: {unit.signature[:100]}"
        if unit.docstring:
            unit_info += f"\nDocstring: {unit.docstring[:200]}"
        
        code_snippet = unit.code[:300] + "..." if len(unit.code) > 300 else unit.code
        unit_info += f"\nCode:\n{code_snippet}"
        
        prompt_parts.append(unit_info)
        prompt_parts.append("")
    
    if heuristic_result:
        prompt_parts.extend([
            f"## Heuristic Analysis (for reference)",
            f"Initial difficulty assessment: {heuristic_result.overall_difficulty.difficulty}",
            f"Confidence: {heuristic_result.overall_difficulty.confidence:.0%}",
            f"Raw score: {heuristic_result.overall_difficulty.raw_score:.2f}",
            f"",
            f"Suggested approach from heuristics:",
        ])
        for suggestion in heuristic_result.suggested_approach[:3]:
            prompt_parts.append(f"  - {suggestion}")
        
        if heuristic_result.positive_signals:
            prompt_parts.append("")
            prompt_parts.append("Positive signals identified:")
            for signal in heuristic_result.positive_signals:
                prompt_parts.append(f"  + {signal}")
        
        if heuristic_result.warning_signals:
            prompt_parts.append("")
            prompt_parts.append("Warning signals:")
            for signal in heuristic_result.warning_signals:
                prompt_parts.append(f"  ! {signal}")
    
    prompt_parts.extend([
        "",
        "## Task",
        "Provide your analysis in JSON format as specified in the system prompt.",
        "Focus on practical guidance for a first-time contributor.",
    ])
    
    return "\n".join(prompt_parts)


def parse_ai_response(response: str) -> dict:
    json_match = re.search(r'\{[\s\S]*\}', response)
    
    if not json_match:
        raise ValueError(f"Could not parse JSON from response: {response[:200]}")
    
    try:
        parsed = json.loads(json_match.group(0))
        
        parsed.setdefault("difficulty", "medium")
        parsed.setdefault("confidence", 0.5)
        parsed.setdefault("reasoning", "")
        parsed.setdefault("suggested_approach", [])
        parsed.setdefault("positive_signals", [])
        parsed.setdefault("warning_signals", [])
        parsed.setdefault("is_good_first_issue", False)
        parsed.setdefault("files_to_focus", [])
        
        if parsed["difficulty"] not in ["easy", "medium", "hard"]:
            parsed["difficulty"] = "medium"
        
        return parsed
    
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON: {e}. Response: {response[:200]}")


class AIScorer:
    def __init__(
        self,
        provider: LLMProvider,
        fallback_scorer: Optional[object] = None,
        timeout: int = 30,
    ):
        self.provider = provider
        self.fallback_scorer = fallback_scorer
        self.timeout = timeout

    def score(self, retrieval: RetrievalResult) -> ScoringResult:
        heuristic_result = None
        
        if self.fallback_scorer:
            heuristic_result = self.fallback_scorer.score(retrieval)
        
        prompt = build_ai_prompt(retrieval, heuristic_result)
        
        try:
            response = self.provider.complete(prompt)
            ai_analysis = parse_ai_response(response)
            
            return self._build_result(retrieval, ai_analysis, heuristic_result)
        
        except Exception as e:
            if heuristic_result:
                return heuristic_result
            
            raise AIScoringError(f"AI scoring failed: {e}") from e

    def _build_result(
        self,
        retrieval: RetrievalResult,
        ai_analysis: dict,
        heuristic_result: Optional[ScoringResult],
    ) -> ScoringResult:
        difficulty_str = ai_analysis.get("difficulty", "medium").lower()
        
        if difficulty_str not in ["easy", "medium", "hard"]:
            difficulty_str = "medium"
        
        difficulty_label = DifficultyLabel(difficulty_str)
        
        difficulty_score = DifficultyScore(
            raw_score=0.5 if difficulty_str == "medium" else (0.25 if difficulty_str == "easy" else 0.75),
            difficulty=difficulty_label.value,
            confidence=ai_analysis.get("confidence", 0.7),
            relative_percentile=None,
        )
        
        positive_signals = ai_analysis.get("positive_signals", [])
        if not positive_signals and heuristic_result:
            positive_signals = heuristic_result.positive_signals
        
        warning_signals = ai_analysis.get("warning_signals", [])
        if not warning_signals and heuristic_result:
            warning_signals = heuristic_result.warning_signals
        
        suggested_approach = ai_analysis.get("suggested_approach", [])
        if not suggested_approach and heuristic_result:
            suggested_approach = heuristic_result.suggested_approach
        
        units = []
        if heuristic_result:
            units = heuristic_result.units
        else:
            units = [
                UnitScore(
                    unit=unit,
                    difficulty_score=0.5,
                    signals=[],
                )
                for unit in retrieval.units
            ]
        
        return ScoringResult(
            issue_title=retrieval.issue.title,
            overall_difficulty=difficulty_score,
            units=units,
            positive_signals=positive_signals[:5],
            warning_signals=warning_signals[:5],
            suggested_approach=suggested_approach[:5],
            is_good_first_issue=ai_analysis.get("is_good_first_issue", False),
        )


class AIScoringError(Exception):
    pass


def create_ai_scorer(
    provider_name: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    fallback_scorer: Optional[object] = None,
    timeout: int = 30,
) -> Optional[AIScorer]:
    from src.analyzer.config import ProviderName
    from src.analyzer.llm_provider import get_provider_instance
    
    try:
        provider_enum = ProviderName(provider_name.lower())
    except ValueError:
        return None
    
    provider = get_provider_instance(provider_enum, api_key=api_key, model=model)
    
    if provider is None:
        return None
    
    return AIScorer(
        provider=provider,
        fallback_scorer=fallback_scorer,
        timeout=timeout,
    )


__all__ = [
    "AIScorer",
    "AIScoringError",
    "build_ai_prompt",
    "parse_ai_response",
    "create_ai_scorer",
]