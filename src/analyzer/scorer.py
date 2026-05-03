from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from src.analyzer.preprocessor import IssueType
from src.analyzer.retriever import RetrievedUnit, RetrievalResult
from src.indexer.dependencies import DEPENDENCY_MANIFEST_HINTS, DependencyProfile
from src.indexer.parser import AssetKind


class DifficultyLabel(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


@dataclass
class DifficultyScore:
    raw_score: float
    difficulty: str
    confidence: float
    relative_percentile: Optional[float] = None


@dataclass
class ContributorSignal:
    is_positive: bool
    message: str


@dataclass
class UnitScore:
    unit: RetrievedUnit
    difficulty_score: float
    signals: list[ContributorSignal] = field(default_factory=list)


@dataclass
class ScoringResult:
    issue_title: str
    overall_difficulty: DifficultyScore
    units: list[UnitScore] = field(default_factory=list)
    positive_signals: list[str] = field(default_factory=list)
    warning_signals: list[str] = field(default_factory=list)
    suggested_approach: list[str] = field(default_factory=list)
    is_good_first_issue: bool = False
    core_problem: str = ""
    strategic_guidance: list[str] = field(default_factory=list)
    why_these_files: list[str] = field(default_factory=list)
    uncertainty_notes: list[str] = field(default_factory=list)


@dataclass
class DependencyImpact:
    adjustment: float = 0.0
    positive_signals: list[str] = field(default_factory=list)
    warning_signals: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    focus_paths: list[str] = field(default_factory=list)


def compute_dependency_impact(retrieval: RetrievalResult) -> DependencyImpact:
    profile = retrieval.dependency_profile
    if profile is None or profile.manifest_count == 0:
        return DependencyImpact()

    complexity = profile.complexity_score()
    impact = DependencyImpact()
    impact.adjustment = min(0.10, 0.03 + (complexity * 0.07))

    if complexity >= 0.35:
        impact.warning_signals.append(
            f"Repository dependency setup is moderately complex ({profile.direct_dependency_count} direct deps across {profile.manifest_count} manifests)"
        )
    else:
        impact.positive_signals.append(
            f"Dependency surface is documented in {profile.manifest_count} manifest{'s' if profile.manifest_count != 1 else ''}"
        )

    manifest_paths = set(profile.manifest_paths)
    explicit_dependency_refs = [
        file_ref.path
        for file_ref in retrieval.issue.mentioned_files
        if file_ref.path in manifest_paths or _looks_like_dependency_manifest(file_ref.path)
    ]
    dependency_units = [
        unit
        for unit in retrieval.units
        if unit.asset_kind == AssetKind.DEPENDENCY.value
    ]

    if dependency_units or explicit_dependency_refs:
        impact.adjustment += 0.16
        impact.warning_signals.append("Dependency or build manifest changes can ripple across the repository")
        focus_candidates = explicit_dependency_refs or [unit.path for unit in dependency_units]
        focus_path = focus_candidates[0]
        impact.focus_paths.append(focus_path)
        impact.suggestions.append(f"Audit dependency constraints and scripts in {focus_path}")
    elif complexity >= 0.55:
        impact.adjustment += 0.04
        impact.warning_signals.append("Repository complexity may hide dependency-side effects outside the first touched file")

    impact.adjustment = min(impact.adjustment, 0.30)

    for flag in profile.risk_flags[:2]:
        impact.warning_signals.append(flag)

    return impact


def apply_dependency_adjustment(
    overall: DifficultyScore,
    all_scores: list[float],
    impact: DependencyImpact,
) -> DifficultyScore:
    if impact.adjustment <= 0:
        return overall

    raw_score = max(0.0, min(1.0, overall.raw_score + impact.adjustment))
    difficulty, confidence = describe_difficulty(raw_score)

    percentile = None
    if all_scores:
        below = sum(1 for score in all_scores if score < raw_score)
        percentile = below / len(all_scores)

    return DifficultyScore(
        raw_score=raw_score,
        difficulty=difficulty,
        confidence=min(confidence + 0.02, 0.95),
        relative_percentile=percentile,
    )


def describe_difficulty(raw_score: float) -> tuple[str, float]:
    if raw_score <= 0.35:
        return DifficultyLabel.EASY.value, min(0.9 - raw_score, 0.95)
    if raw_score <= 0.65:
        return DifficultyLabel.MEDIUM.value, 0.85
    return DifficultyLabel.HARD.value, min(raw_score - 0.65 + 0.7, 0.95)


def _looks_like_dependency_manifest(path: str) -> bool:
    name = path.replace("\\", "/").split("/")[-1].lower()
    return name in DEPENDENCY_MANIFEST_HINTS or name.startswith("requirements")


class HeuristicScorer:
    def __init__(self, db_path: str = ".data/index.lance"):
        self.db_path = db_path
        self._all_scores: list[float] = []

    def score(self, retrieval: RetrievalResult) -> ScoringResult:
        unit_scores = self._score_units(retrieval.units)
        self._all_scores = [unit_score.difficulty_score for unit_score in unit_scores]

        overall = self._compute_overall_score(unit_scores)
        dependency_impact = compute_dependency_impact(retrieval)
        overall = apply_dependency_adjustment(overall, self._all_scores, dependency_impact)

        positive_signals, warning_signals = self._extract_signals(unit_scores, retrieval, dependency_impact)
        suggested = self._generate_suggestions(unit_scores, retrieval, dependency_impact)
        why_these_files = self._explain_file_focus(unit_scores, dependency_impact)
        uncertainty_notes = self._build_uncertainty_notes(retrieval)
        is_good_first = self._assess_good_first(overall, positive_signals, warning_signals)

        return ScoringResult(
            issue_title=retrieval.issue.title,
            overall_difficulty=overall,
            units=unit_scores,
            positive_signals=positive_signals,
            warning_signals=warning_signals,
            suggested_approach=suggested,
            is_good_first_issue=is_good_first,
            why_these_files=why_these_files,
            uncertainty_notes=uncertainty_notes,
        )

    def _score_units(self, units: list[RetrievedUnit]) -> list[UnitScore]:
        scored = []
        for unit in units:
            score = self._compute_unit_score(unit)
            signals = self._extract_unit_signals(unit, score)
            scored.append(UnitScore(unit=unit, difficulty_score=score, signals=signals))
        return scored

    def _compute_unit_score(self, unit: RetrievedUnit) -> float:
        if unit.asset_kind != AssetKind.CODE.value:
            return self._compute_non_code_score(unit)

        score = 0.0
        if unit.unit_type == "function":
            score += 0.1
        elif unit.unit_type == "method":
            score += 0.15
        elif unit.unit_type == "class":
            score += 0.2

        loc = unit.code.count("\n")
        score += min(loc / 500, 0.3)
        if unit.is_test:
            score *= 0.7
        if unit.docstring:
            score *= 0.9
        if unit.signature and "(" in unit.signature:
            score *= 0.95

        return min(score, 1.0)

    def _compute_non_code_score(self, unit: RetrievedUnit) -> float:
        loc = unit.code.count("\n")
        if unit.asset_kind == AssetKind.DOCS.value:
            score = 0.12
        elif unit.asset_kind == AssetKind.WORKFLOW.value:
            score = 0.3
        elif unit.asset_kind == AssetKind.DEPENDENCY.value:
            score = 0.36
        else:
            score = 0.24

        if unit.match_type == "explicit":
            score -= 0.08
        elif unit.match_type == "keyword":
            score -= 0.03

        score += min(loc / 800, 0.18)
        return min(max(score, 0.05), 1.0)

    def _extract_unit_signals(self, unit: RetrievedUnit, score: float) -> list[ContributorSignal]:
        signals = []
        if unit.asset_kind != AssetKind.CODE.value:
            if unit.asset_kind == AssetKind.DOCS.value:
                signals.append(ContributorSignal(True, "Documentation change is easier to validate"))
            elif unit.asset_kind == AssetKind.WORKFLOW.value:
                signals.append(ContributorSignal(False, "CI workflow changes can affect automation"))
            elif unit.asset_kind == AssetKind.DEPENDENCY.value:
                signals.append(ContributorSignal(False, "Dependency manifest changes can affect build stability"))
            else:
                signals.append(ContributorSignal(True, "Configuration scope is usually file-local"))
            return signals

        if unit.is_test:
            signals.append(ContributorSignal(True, "Test file - changes are verifiable"))
        if unit.docstring:
            signals.append(ContributorSignal(True, "Has documentation"))
        if unit.signature and len(unit.signature) < 100:
            signals.append(ContributorSignal(True, "Clear interface"))
        if unit.match_reasons:
            signals.append(ContributorSignal(True, f"Matched because: {', '.join(unit.match_reasons[:2])}"))
        if unit.unit_type == "function" and score < 0.3:
            signals.append(ContributorSignal(True, "Isolated change possible"))
        if unit.unit_type == "class" and score > 0.5:
            signals.append(ContributorSignal(False, "May require class-level changes"))
        return signals

    def _compute_overall_score(self, unit_scores: list[UnitScore]) -> DifficultyScore:
        if not unit_scores:
            return DifficultyScore(raw_score=0.0, difficulty="unknown", confidence=0.0)

        scores = [unit_score.difficulty_score for unit_score in unit_scores]
        avg_score = sum(scores) / len(scores)
        max_score = max(scores)
        raw_score = (avg_score * 0.4) + (max_score * 0.6)

        difficulty, confidence = describe_difficulty(raw_score)
        percentile = None
        if self._all_scores:
            below = sum(1 for score in self._all_scores if score < raw_score)
            percentile = below / len(self._all_scores)

        return DifficultyScore(
            raw_score=raw_score,
            difficulty=difficulty,
            confidence=confidence,
            relative_percentile=percentile,
        )

    def _extract_signals(
        self,
        unit_scores: list[UnitScore],
        retrieval: RetrievalResult,
        dependency_impact: DependencyImpact,
    ) -> tuple[list[str], list[str]]:
        all_signals = []
        for unit_score in unit_scores:
            all_signals.extend(unit_score.signals)

        positive = list(dict.fromkeys(signal.message for signal in all_signals if signal.is_positive))
        warnings = list(dict.fromkeys(signal.message for signal in all_signals if not signal.is_positive))

        if retrieval.issue.issue_type == IssueType.BUG:
            positive.insert(0, "Bug report with clear scope")
        if retrieval.issue.error_patterns:
            positive.insert(1, "Stack trace provides concrete debugging clues")
        if not retrieval.issue.mentioned_files:
            warnings.append("Issue does not mention a concrete file path")
        if len(retrieval.units) < 2:
            warnings.append("Limited retrieval context may hide related call sites")

        positive.extend(dependency_impact.positive_signals)
        warnings.extend(dependency_impact.warning_signals)

        return list(dict.fromkeys(positive))[:5], list(dict.fromkeys(warnings))[:5]

    def _generate_suggestions(
        self,
        unit_scores: list[UnitScore],
        retrieval: RetrievalResult,
        dependency_impact: DependencyImpact,
    ) -> list[str]:
        if not unit_scores:
            suggestions = ["No relevant code found in index"]
        else:
            suggestions = []
            ranked = sorted(unit_scores, key=lambda item: item.difficulty_score)
            for index, unit_score in enumerate(ranked[:3]):
                unit = unit_score.unit
                if unit.asset_kind == AssetKind.DOCS.value:
                    suggestions.append(f"{index + 1}. Start in {unit.path}")
                elif unit.asset_kind == AssetKind.WORKFLOW.value:
                    suggestions.append(f"{index + 1}. Check {unit.path} for related workflow changes")
                elif unit.asset_kind == AssetKind.DEPENDENCY.value:
                    suggestions.append(f"{index + 1}. Review dependency and build rules in {unit.path}")
                elif unit.asset_kind == AssetKind.CONFIG.value:
                    suggestions.append(f"{index + 1}. Check {unit.path} for related configuration")
                elif unit.name and unit.name != unit.path:
                    suggestions.append(f"{index + 1}. Start in {unit.path} -> {unit.name}")
                else:
                    suggestions.append(f"{index + 1}. Start in {unit.path}")

            if retrieval.issue.issue_type == IssueType.BUG:
                files = [item.unit.path for item in ranked[:3] if item.unit.asset_kind == AssetKind.CODE.value]
                if files:
                    test_hints = self._find_test_files(files[0])
                    if test_hints:
                        suggestions.append(f"Test: {test_hints}")

        if retrieval.issue.stack_traces:
            suggestions.append("Validate the fix against the reported stack trace or reproduction path")

        suggestions.extend(dependency_impact.suggestions)
        return list(dict.fromkeys(suggestions))[:5]

    def _assess_good_first(
        self,
        overall: DifficultyScore,
        positive_signals: list[str],
        warning_signals: list[str],
    ) -> bool:
        return (
            overall.difficulty == DifficultyLabel.EASY.value
            and len(warning_signals) <= 2
            and any("verifiable" in signal.lower() or "isolated" in signal.lower() for signal in positive_signals)
        )

    def _find_test_files(self, path: str) -> str | None:
        filename = path.rsplit("/", 1)[-1]
        if filename.endswith(".py"):
            return f"pytest tests/test_{filename[:-3]}.py"
        return None

    def _explain_file_focus(
        self,
        unit_scores: list[UnitScore],
        dependency_impact: DependencyImpact,
    ) -> list[str]:
        explanations = []
        for unit_score in unit_scores[:3]:
            unit = unit_score.unit
            reasons = unit.match_reasons[:2] or ["high retrieval score"]
            label = unit.name if unit.name and unit.name != unit.path else unit.path
            explanations.append(f"{label} is relevant because of {', '.join(reasons)}")

        for focus_path in dependency_impact.focus_paths[:1]:
            explanations.append(f"{focus_path} matters because the issue touches dependency or build configuration")

        return explanations[:5]

    def _build_uncertainty_notes(self, retrieval: RetrievalResult) -> list[str]:
        notes = []
        if not retrieval.issue.mentioned_files:
            notes.append("The issue does not name a specific file, so file focus is inferred from retrieval.")
        if len(retrieval.units) < 2:
            notes.append("Only a small amount of relevant code was retrieved from the index.")
        if retrieval.issue.issue_type == IssueType.UNKNOWN:
            notes.append("The issue type is ambiguous, so difficulty may shift after reproducing the bug.")
        if retrieval.dependency_profile is None:
            notes.append("Dependency profile was unavailable, so repository coupling may be underestimated.")
        return notes[:3]


__all__ = [
    "DifficultyLabel",
    "DifficultyScore",
    "ContributorSignal",
    "UnitScore",
    "ScoringResult",
    "DependencyImpact",
    "compute_dependency_impact",
    "apply_dependency_adjustment",
    "describe_difficulty",
    "HeuristicScorer",
]
