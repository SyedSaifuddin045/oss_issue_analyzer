from __future__ import annotations

from src.analyzer.preprocessor import ProcessedIssue, IssueType
from src.analyzer.scorer import (
    DifficultyScore,
    DifficultyLabel,
    apply_dependency_adjustment,
    compute_dependency_impact,
    describe_difficulty,
)
from src.analyzer.retriever import RetrievalResult
from src.indexer.parser import AssetKind


class QuickHeuristicScorer:
    """Fast, local scoring using issue metadata and lightweight code retrieval."""

    def score(
        self,
        issue: ProcessedIssue,
        retrieval: RetrievalResult | None = None,
        labels: list[str] | None = None,
    ) -> DifficultyScore:
        score = 0.5

        labels = labels or []
        labels_lower = [label.lower() for label in labels]

        if any("good first" in label for label in labels_lower):
            score -= 0.3
        if any("beginner" in label for label in labels_lower):
            score -= 0.2
        if any("help wanted" in label for label in labels_lower):
            score -= 0.15
        if any("enhancement" in label for label in labels_lower):
            score += 0.1
        if any("feature" in label for label in labels_lower) and issue.issue_type == IssueType.FEATURE:
            score += 0.05

        if issue.issue_type == IssueType.BUG:
            score -= 0.1
        elif issue.issue_type == IssueType.DOCS:
            score -= 0.25
        elif issue.issue_type == IssueType.REFACTOR:
            score += 0.15

        body_len = len(issue.body)
        if body_len < 300:
            score -= 0.1
        elif body_len > 3000:
            score += 0.15

        if issue.error_patterns:
            score -= 0.05

        has_code = False
        if retrieval and retrieval.units:
            has_code = True
            code_scores = [self._score_unit(unit) for unit in retrieval.units[:3]]
            if code_scores:
                code_avg = sum(code_scores) / len(code_scores)
                score = (score * 0.4) + (code_avg * 0.6)

        result = self._to_difficulty_score(score, has_code=has_code)
        if retrieval:
            impact = compute_dependency_impact(retrieval)
            result = apply_dependency_adjustment(result, [], impact)
            if isinstance(result.difficulty, DifficultyLabel):
                result.difficulty = DifficultyLabel(result.difficulty.value)
            else:
                result.difficulty = DifficultyLabel(str(result.difficulty))
        return result

    def _score_unit(self, unit) -> float:
        if unit.asset_kind != AssetKind.CODE.value:
            return self._score_non_code_unit(unit)

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

    def _score_non_code_unit(self, unit) -> float:
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

    def _to_difficulty_score(self, raw: float, has_code: bool) -> DifficultyScore:
        raw = max(0.0, min(1.0, raw))
        difficulty, confidence = describe_difficulty(raw)

        if not has_code:
            confidence = max(confidence - 0.30, 0.5)
        elif difficulty == DifficultyLabel.EASY.value:
            confidence = max(confidence - 0.05, 0.7)

        return DifficultyScore(
            raw_score=raw,
            difficulty=DifficultyLabel(difficulty),
            confidence=confidence,
        )


__all__ = ["QuickHeuristicScorer"]
