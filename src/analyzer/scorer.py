from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from src.analyzer.retriever import RetrievedUnit, RetrievalResult


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


class HeuristicScorer:
    def __init__(self, db_path: str = ".data/index.lance"):
        self.db_path = db_path
        self._all_scores: list[float] = []

    def score(self, retrieval: RetrievalResult) -> ScoringResult:
        unit_scores = self._score_units(retrieval.units)
        
        self._all_scores = [us.difficulty_score for us in unit_scores]
        
        overall = self._compute_overall_score(unit_scores)
        
        positive_signals, warning_signals = self._extract_signals(unit_scores, retrieval)
        
        suggested = self._generate_suggestions(unit_scores, retrieval)
        
        is_good_first = self._assess_good_first(
            overall, positive_signals, warning_signals
        )

        return ScoringResult(
            issue_title=retrieval.issue.title,
            overall_difficulty=overall,
            units=unit_scores,
            positive_signals=positive_signals,
            warning_signals=warning_signals,
            suggested_approach=suggested,
            is_good_first_issue=is_good_first,
        )

    def _score_units(
        self, units: list[RetrievedUnit]
    ) -> list[UnitScore]:
        scored = []
        
        for unit in units:
            score = self._compute_unit_score(unit)
            signals = self._extract_unit_signals(unit, score)
            
            scored.append(
                UnitScore(
                    unit=unit,
                    difficulty_score=score,
                    signals=signals,
                )
            )

        return scored

    def _compute_unit_score(self, unit: RetrievedUnit) -> float:
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

    def _extract_unit_signals(
        self, unit: RetrievedUnit, score: float
    ) -> list[ContributorSignal]:
        signals = []
        
        if unit.is_test:
            signals.append(
                ContributorSignal(
                    is_positive=True,
                    message=f"Test file - changes are verifiable"
                )
            )
        
        if unit.docstring:
            signals.append(
                ContributorSignal(
                    is_positive=True,
                    message="Has documentation"
                )
            )
        
        if unit.signature and len(unit.signature) < 100:
            signals.append(
                ContributorSignal(
                    is_positive=True,
                    message="Clear interface"
                )
            )
        
        if unit.unit_type == "function" and score < 0.3:
            signals.append(
                ContributorSignal(
                    is_positive=True,
                    message="Isolated change possible"
                )
            )
        
        if unit.unit_type == "class" and score > 0.5:
            signals.append(
                ContributorSignal(
                    is_positive=False,
                    message="May require class-level changes"
                )
            )

        return signals

    def _compute_overall_score(
        self, unit_scores: list[UnitScore]
    ) -> DifficultyScore:
        if not unit_scores:
            return DifficultyScore(
                raw_score=0.0,
                difficulty="unknown",
                confidence=0.0
            )

        scores = [us.difficulty_score for us in unit_scores]
        
        avg_score = sum(scores) / len(scores)
        max_score = max(scores)
        
        raw_score = (avg_score * 0.4) + (max_score * 0.6)
        
        if raw_score <= 0.35:
            difficulty = "easy"
            confidence = 0.9 - raw_score
        elif raw_score <= 0.65:
            difficulty = "medium"
            confidence = 0.85
        else:
            difficulty = "hard"
            confidence = raw_score - 0.65 + 0.7

        percentile = None
        if self._all_scores:
            below = sum(1 for s in self._all_scores if s < raw_score)
            percentile = below / len(self._all_scores) if self._all_scores else 0.0

        return DifficultyScore(
            raw_score=raw_score,
            difficulty=difficulty,
            confidence=min(confidence, 0.95),
            relative_percentile=percentile,
        )

    def _extract_signals(
        self,
        unit_scores: list[UnitScore],
        retrieval: RetrievalResult,
    ) -> tuple[list[str], list[str]]:
        positive = []
        warnings = []
        
        all_signals = []
        for us in unit_scores:
            all_signals.extend(us.signals)

        positive_msgs = [s.message for s in all_signals if s.is_positive]
        warning_msgs = [s.message for s in all_signals if not s.is_positive]

        unique_positive = list(dict.fromkeys(positive_msgs))
        unique_warning = list(dict.fromkeys(warning_msgs))

        if retrieval.issue.issue_type == "bug":
            unique_positive.append("Bug report with clear scope")
        
        if retrieval.issue.error_patterns:
            unique_warning.append("Error trace provides debugging hints")

        return unique_positive[:5], unique_warning[:5]

    def _generate_suggestions(
        self,
        unit_scores: list[UnitScore],
        retrieval: RetrievalResult,
    ) -> list[str]:
        suggestions = []
        
        if not unit_scores:
            return ["No relevant code found in index"]

        sorted_units = sorted(
            unit_scores,
            key=lambda x: x.difficulty_score
        )

        for i, us in enumerate(sorted_units[:3]):
            if us.unit.name:
                suggestions.append(
                    f"{i+1}. Start in {us.unit.path} -> {us.unit.name}"
                )
            else:
                suggestions.append(
                    f"{i+1}. Start in {us.unit.path}"
                )

        if retrieval.issue.issue_type == "bug":
            files = list(set(u.unit.path for u in sorted_units[:3] if u.unit.path))
            if files:
                test_hints = self._find_test_files(files[0])
                if test_hints:
                    suggestions.append(f"Test: {test_hints}")

        return suggestions

    def _find_test_files(self, file_path: str) -> str:
        import os
        path = file_path
        
        if "/test_" in path or path.endswith("test.py"):
            return path
        
        parts = path.rsplit("/", 1)
        if len(parts) == 2:
            directory, filename = parts
            test_name = f"{directory}/test_{filename}"
            if os.path.exists(test_name):
                return test_name
        
        return f"Check test_{file_path}"

    def _assess_good_first(
        self,
        overall: DifficultyScore,
        positive: list[str],
        warnings: list[str],
    ) -> bool:
        if overall.difficulty != "easy":
            return False
        
        if "Isolated change possible" not in positive:
            return False
        
        if len(warnings) > 2:
            return False

        return True


__all__ = [
    "HeuristicScorer",
    "DifficultyScore",
    "ContributorSignal",
    "UnitScore",
    "ScoringResult",
]