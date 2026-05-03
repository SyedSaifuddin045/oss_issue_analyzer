from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.analyzer.llm_provider import LLMProvider, LLMRequest
from src.analyzer.retriever import RetrievalResult, RetrievedUnit
from src.analyzer.scorer import DifficultyLabel, DifficultyScore, ScoringResult, UnitScore


ANALYSIS_SCHEMA_VERSION = "analysis-v2"

SYSTEM_PROMPT = """You are a senior open source maintainer mentoring a first-time contributor.

Return exactly one JSON object and nothing else.

Your job:
- Estimate how difficult this issue is for a newcomer in this specific repository.
- Use only the provided evidence from the issue, comments, and retrieved code context.
- Prefer precise, evidence-backed advice over generic software guidance.
- When the evidence is thin or ambiguous, say so in uncertainty_notes instead of making up certainty.

Required JSON schema:
{
  "difficulty": "easy" | "medium" | "hard",
  "confidence": 0.0-1.0,
  "core_problem": "1-2 sentences on the likely underlying problem",
  "strategic_guidance": ["4-7 mentoring bullets"],
  "suggested_approach": ["3-5 actionable steps"],
  "positive_signals": ["short signals"],
  "warning_signals": ["short warnings"],
  "is_good_first_issue": true | false,
  "files_to_focus": ["path/to/file.py"],
  "why_these_files": ["why each file matters"],
  "uncertainty_notes": ["what is uncertain or missing"]
}

Rules:
- No extra fields.
- No nested objects.
- strategic_guidance should explain what to inspect, trace, or be careful about.
- suggested_approach should be concrete and sequenced.
- why_these_files must tie file focus back to issue evidence or retrieved code context.
- uncertainty_notes should be empty if the evidence is strong.
"""


class AIAnalysisSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    difficulty: str
    confidence: float
    core_problem: str
    strategic_guidance: list[str] = Field(min_length=4, max_length=7)
    suggested_approach: list[str] = Field(min_length=3, max_length=5)
    positive_signals: list[str] = Field(default_factory=list)
    warning_signals: list[str] = Field(default_factory=list)
    is_good_first_issue: bool = False
    files_to_focus: list[str] = Field(default_factory=list)
    why_these_files: list[str] = Field(default_factory=list)
    uncertainty_notes: list[str] = Field(default_factory=list)


@dataclass
class PackedContextUnit:
    unit: RetrievedUnit
    reason: str
    excerpt: str


def build_ai_prompt(
    retrieval: RetrievalResult,
    heuristic_result: Optional[ScoringResult] = None,
    context_unit_budget: int = 8,
) -> str:
    issue = retrieval.issue
    packed_units = pack_context_units(retrieval, context_unit_budget=context_unit_budget)

    prompt_parts = [
        "# Issue Analysis Request",
        "",
        "## Issue Overview",
        f"Title: {issue.title}",
        f"Type: {issue.issue_type.value.upper() if hasattr(issue.issue_type, 'value') else str(issue.issue_type).upper()}",
        "",
    ]

    if issue.body:
        prompt_parts.append("Body:")
        prompt_parts.append(issue.body[:1800])
        prompt_parts.append("")

    if issue.mentioned_files:
        prompt_parts.append("Mentioned files: " + ", ".join(file_ref.path for file_ref in issue.mentioned_files[:6]))
    if issue.mentioned_symbols:
        prompt_parts.append("Mentioned symbols: " + ", ".join(symbol.name for symbol in issue.mentioned_symbols[:8]))
    if issue.error_patterns:
        prompt_parts.append("Error patterns: " + ", ".join(error.pattern for error in issue.error_patterns[:4]))
    if issue.stack_traces:
        prompt_parts.append("Stack trace clues:")
        prompt_parts.extend(f"- {trace[:220]}" for trace in issue.stack_traces[:3])
    if issue.code_blocks:
        prompt_parts.append("Technical snippets from the issue:")
        prompt_parts.extend(f"```text\n{block[:320]}\n```" for block in issue.code_blocks[:2])
    prompt_parts.append("")

    if issue.comments:
        prompt_parts.append(f"## Issue Discussion & Comments ({len(issue.comments)} comments)")
        for comment in issue.comments[:5]:
            role = "maintainer" if comment.is_maintainer else "community"
            prompt_parts.append(
                f"- [{role} | @{comment.author} | reactions={comment.reactions}] {comment.body[:420]}"
            )
        prompt_parts.append("")

    if retrieval.dependency_profile and retrieval.dependency_profile.manifest_count:
        profile = retrieval.dependency_profile
        prompt_parts.extend(
            [
                "## Repository Dependency Context",
                f"Manifests: {profile.manifest_count}",
                f"Ecosystems: {', '.join(profile.ecosystems) or 'unknown'}",
                f"Direct dependencies: {profile.direct_dependency_count}",
                f"Dev dependencies: {profile.dev_dependency_count}",
            ]
        )
        if profile.risk_flags:
            prompt_parts.append("Dependency risks: " + "; ".join(profile.risk_flags[:3]))
        prompt_parts.append("")

    prompt_parts.append(f"## Ranked Code Context ({len(packed_units)} selected units)")
    for index, packed in enumerate(packed_units, start=1):
        unit = packed.unit
        label = f"{unit.path} -> {unit.name}" if unit.name and unit.name != unit.path else unit.path
        prompt_parts.extend(
            [
                f"### Context {index}: {label}",
                f"Match type: {unit.match_type}",
                f"Why selected: {packed.reason}",
                f"Signature: {unit.signature[:140]}" if unit.signature else "Signature: (not available)",
                f"Docstring: {unit.docstring[:180]}" if unit.docstring else "Docstring: (not available)",
                "Code excerpt:",
                packed.excerpt,
                "",
            ]
        )

    if heuristic_result:
        prompt_parts.extend(
            [
                "## Heuristic Prior (reference only)",
                f"Difficulty: {heuristic_result.overall_difficulty.difficulty}",
                f"Confidence: {heuristic_result.overall_difficulty.confidence:.0%}",
            ]
        )
        if heuristic_result.positive_signals:
            prompt_parts.append("Positive signals: " + "; ".join(heuristic_result.positive_signals[:4]))
        if heuristic_result.warning_signals:
            prompt_parts.append("Warning signals: " + "; ".join(heuristic_result.warning_signals[:4]))
        if heuristic_result.suggested_approach:
            prompt_parts.append("Suggested first steps: " + "; ".join(heuristic_result.suggested_approach[:3]))
        prompt_parts.append("")

    prompt_parts.extend(
        [
            "## Task",
            "Use the issue evidence and the ranked code context to mentor a first-time contributor.",
            "Return exactly one JSON object matching the system schema.",
            "If a file is important, explain why it matters in why_these_files.",
            "If confidence should be limited, explain the gap in uncertainty_notes.",
        ]
    )

    return "\n".join(prompt_parts)


def build_ai_request(
    retrieval: RetrievalResult,
    heuristic_result: Optional[ScoringResult] = None,
    temperature: float = 0.1,
    max_tokens: int = 1200,
    context_unit_budget: int = 8,
) -> LLMRequest:
    return LLMRequest(
        system=SYSTEM_PROMPT,
        user=build_ai_prompt(
            retrieval,
            heuristic_result=heuristic_result,
            context_unit_budget=context_unit_budget,
        ),
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )


def pack_context_units(
    retrieval: RetrievalResult,
    context_unit_budget: int = 8,
    char_budget: int = 4200,
) -> list[PackedContextUnit]:
    ranked = sorted(
        retrieval.units,
        key=lambda unit: (
            unit.score,
            len(unit.match_reasons),
            1 if unit.is_test else 0,
        ),
        reverse=True,
    )

    packed: list[PackedContextUnit] = []
    chars_used = 0
    per_path: dict[str, int] = {}
    for unit in ranked:
        if len(packed) >= context_unit_budget:
            break
        if per_path.get(unit.path, 0) >= 2 and not unit.is_test:
            continue

        excerpt = _format_code_excerpt(unit)
        candidate_cost = len(excerpt) + len(unit.path) + len(unit.signature or "")
        if packed and chars_used + candidate_cost > char_budget:
            continue

        packed.append(
            PackedContextUnit(
                unit=unit,
                reason=_build_selection_reason(unit),
                excerpt=excerpt,
            )
        )
        chars_used += candidate_cost
        per_path[unit.path] = per_path.get(unit.path, 0) + 1

    return packed


def _build_selection_reason(unit: RetrievedUnit) -> str:
    reasons = list(unit.match_reasons)
    if unit.is_test:
        reasons.append("it gives a fast way to validate the fix")
    if unit.docstring:
        reasons.append("the interface is documented")
    if not reasons:
        reasons.append("it scored highly in retrieval")
    return ", ".join(dict.fromkeys(reasons))


def _format_code_excerpt(unit: RetrievedUnit) -> str:
    code = unit.code.strip()
    if len(code) > 500:
        code = code[:500] + "..."
    return code or "(no code excerpt available)"


def parse_ai_response(response: str) -> dict:
    json_text = _extract_json_object(response)
    try:
        parsed = AIAnalysisSchema.model_validate_json(json_text)
    except ValidationError as exc:
        raise ValueError(f"AI response did not match schema: {exc}") from exc

    data = parsed.model_dump()
    difficulty = str(data["difficulty"]).lower()
    if difficulty not in {"easy", "medium", "hard"}:
        raise ValueError(f"Invalid difficulty '{data['difficulty']}'")
    data["difficulty"] = difficulty
    data["confidence"] = max(0.0, min(float(data["confidence"]), 1.0))
    return data


def _prefer_ai_value(ai_analysis: dict, key: str, fallback):
    if key in ai_analysis:
        return ai_analysis[key]
    return fallback


def _extract_json_object(response: str) -> str:
    match = re.search(r"\{[\s\S]*\}", response)
    if not match:
        raise ValueError(f"Could not parse JSON from response: {response[:200]}")
    return match.group(0)


class AIScorer:
    def __init__(
        self,
        provider: LLMProvider,
        fallback_scorer: Optional[object] = None,
        timeout: int = 30,
        temperature: float = 0.1,
        max_tokens: int = 1200,
        context_unit_budget: int = 8,
    ):
        self.provider = provider
        self.fallback_scorer = fallback_scorer
        self.timeout = timeout
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.context_unit_budget = context_unit_budget

    def score(self, retrieval: RetrievalResult) -> ScoringResult:
        heuristic_result = self.fallback_scorer.score(retrieval) if self.fallback_scorer else None
        request = build_ai_request(
            retrieval,
            heuristic_result=heuristic_result,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            context_unit_budget=self.context_unit_budget,
        )

        try:
            response = self.provider.complete(request)
            ai_analysis = parse_ai_response(response.content)
            return self._build_result(retrieval, ai_analysis, heuristic_result)
        except Exception as exc:
            if heuristic_result:
                return heuristic_result
            raise AIScoringError(f"AI scoring failed: {exc}") from exc

    def get_analysis_signature(self) -> str:
        return (
            f"{ANALYSIS_SCHEMA_VERSION}:"
            f"{self.provider.get_provider_name()}:"
            f"{self.provider.get_model_name()}:"
            f"{self.temperature:.2f}:"
            f"{self.max_tokens}:"
            f"{self.context_unit_budget}"
        )

    def _build_result(
        self,
        retrieval: RetrievalResult,
        ai_analysis: dict,
        heuristic_result: Optional[ScoringResult],
    ) -> ScoringResult:
        difficulty_str = ai_analysis.get("difficulty", DifficultyLabel.MEDIUM.value).lower()
        if difficulty_str not in {
            DifficultyLabel.EASY.value,
            DifficultyLabel.MEDIUM.value,
            DifficultyLabel.HARD.value,
        }:
            difficulty_str = DifficultyLabel.MEDIUM.value

        difficulty_score = DifficultyScore(
            raw_score=0.5 if difficulty_str == "medium" else (0.25 if difficulty_str == "easy" else 0.75),
            difficulty=difficulty_str,
            confidence=ai_analysis.get("confidence", 0.7),
            relative_percentile=(
                heuristic_result.overall_difficulty.relative_percentile
                if heuristic_result
                else None
            ),
        )

        positive_signals = _prefer_ai_value(
            ai_analysis,
            "positive_signals",
            heuristic_result.positive_signals if heuristic_result else [],
        )
        warning_signals = _prefer_ai_value(
            ai_analysis,
            "warning_signals",
            heuristic_result.warning_signals if heuristic_result else [],
        )
        suggested_approach = _prefer_ai_value(
            ai_analysis,
            "suggested_approach",
            heuristic_result.suggested_approach if heuristic_result else [],
        )
        why_these_files = _prefer_ai_value(
            ai_analysis,
            "why_these_files",
            heuristic_result.why_these_files if heuristic_result else [],
        )
        uncertainty_notes = _prefer_ai_value(
            ai_analysis,
            "uncertainty_notes",
            heuristic_result.uncertainty_notes if heuristic_result else [],
        )

        if heuristic_result:
            units = heuristic_result.units
        else:
            units = [
                UnitScore(unit=unit, difficulty_score=0.5, signals=[])
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
            core_problem=ai_analysis.get("core_problem", ""),
            strategic_guidance=ai_analysis.get("strategic_guidance", [])[:7],
            why_these_files=why_these_files[:5],
            uncertainty_notes=uncertainty_notes[:3],
        )


class AIScoringError(Exception):
    pass


def create_ai_scorer(
    provider_name: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    fallback_scorer: Optional[object] = None,
    timeout: int = 30,
    temperature: float = 0.1,
    max_tokens: int = 1200,
    context_unit_budget: int = 8,
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
        temperature=temperature,
        max_tokens=max_tokens,
        context_unit_budget=context_unit_budget,
    )


__all__ = [
    "ANALYSIS_SCHEMA_VERSION",
    "AIScorer",
    "AIScoringError",
    "build_ai_prompt",
    "build_ai_request",
    "parse_ai_response",
    "create_ai_scorer",
    "pack_context_units",
]
