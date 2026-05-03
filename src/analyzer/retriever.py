from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from src.analyzer.preprocessor import IssueType, ProcessedIssue
from src.indexer.dependencies import DependencyProfile
from src.indexer.parser import AssetKind

if TYPE_CHECKING:
    from src.indexer.embedder import Embedder


def get_embedder(model: str):
    from src.indexer.embedder import get_embedder as load_embedder

    return load_embedder(model)


@dataclass
class RetrievedUnit:
    id: str
    path: str
    name: Optional[str]
    unit_type: str
    language: str
    start_line: int
    end_line: int
    signature: Optional[str]
    docstring: Optional[str]
    code: str
    asset_kind: str = AssetKind.CODE.value
    score: float = 0.0
    match_type: str = "semantic"
    is_test: bool = False
    match_reasons: list[str] = field(default_factory=list)


@dataclass
class RetrievalResult:
    issue: ProcessedIssue
    units: list[RetrievedUnit] = field(default_factory=list)
    search_stats: dict = field(default_factory=dict)
    dependency_profile: DependencyProfile | None = None


class HybridRetriever:
    WEIGHTS = {
        "semantic": 0.50,
        "keyword": 0.30,
        "explicit": 0.20,
    }

    def __init__(
        self,
        db_path: str = ".data/index.lance",
        embedder: Optional[Embedder] = None,
    ):
        self.db_path = db_path
        self._embedder = embedder
        self._vector_store = None
        self._repo_id: Optional[str] = None
        self._dependency_profile: DependencyProfile | None = None

    @property
    def embedder(self) -> Embedder:
        if self._embedder is None:
            self._embedder = get_embedder("minilm")
        return self._embedder

    @property
    def vector_store(self):
        if self._vector_store is None:
            from src.indexer.storage import VectorStore
            self._vector_store = VectorStore(self.db_path)
        return self._vector_store

    def set_repo(self, repo_id: str) -> None:
        self._repo_id = repo_id
        self._dependency_profile = self.vector_store.get_dependency_profile(repo_id)

    def search(
        self,
        issue: ProcessedIssue,
        repo_id: str,
        limit: int = 10,
    ) -> RetrievalResult:
        if self._dependency_profile is None or self._repo_id != repo_id:
            self.set_repo(repo_id)

        semantic_results = self._semantic_search(issue, repo_id, max(limit * 3, 12))
        keyword_results = self._keyword_search(issue, repo_id, max(limit * 2, 8))
        explicit_results = self._explicit_search(issue, repo_id, max(limit, 5))

        combined = self._combine_results(
            issue,
            semantic_results,
            keyword_results,
            explicit_results,
            limit,
        )

        search_stats = {
            "semantic_count": len(semantic_results),
            "keyword_count": len(keyword_results),
            "explicit_count": len(explicit_results),
            "selected_count": len(combined),
        }

        return RetrievalResult(
            issue=issue,
            units=combined,
            search_stats=search_stats,
            dependency_profile=self._dependency_profile,
        )

    def _semantic_search(
        self,
        issue: ProcessedIssue,
        repo_id: str,
        limit: int,
    ) -> list[RetrievedUnit]:
        try:
            query_embedding = self.embedder.embed(issue.searchable_text)
        except Exception:
            return []

        results = self.vector_store.search(
            query=issue.searchable_text,
            query_embedding=query_embedding,
            repo_id=repo_id,
            limit=limit,
        )

        units = []
        for record in results:
            reasons = ["semantic similarity"]
            if self._is_exact_symbol_match(issue, record.get("name")):
                reasons.append("exact symbol mention")
            if self._is_explicitly_mentioned(issue, record.get("path", "")):
                reasons.append("explicit file mention")
            units.append(
                self._build_unit(
                    record,
                    issue,
                    score=self._adjust_semantic_score(
                        record.get("_score", 0.0),
                        record.get("asset_kind", AssetKind.CODE.value),
                        record.get("path", ""),
                        issue,
                    ),
                    match_type="semantic",
                    reasons=reasons,
                )
            )
        return units

    def _keyword_search(
        self,
        issue: ProcessedIssue,
        repo_id: str,
        limit: int,
    ) -> list[RetrievedUnit]:
        units = []

        for symbol in issue.mentioned_symbols[:12]:
            results = self.vector_store.search_by_text(query=symbol.name, repo_id=repo_id, limit=4)
            for record in results:
                name = record.get("name")
                if not name:
                    continue
                if name == symbol.name:
                    reasons = ["exact symbol mention", "keyword match"]
                    score = 0.78
                elif symbol.name.lower() in name.lower():
                    reasons = ["partial symbol match", "keyword match"]
                    score = 0.66
                else:
                    continue
                units.append(
                    self._build_unit(
                        record,
                        issue,
                        score=score,
                        match_type="keyword",
                        reasons=reasons,
                    )
                )

        return units[:limit]

    def _explicit_search(
        self,
        issue: ProcessedIssue,
        repo_id: str,
        limit: int,
    ) -> list[RetrievedUnit]:
        units = []

        for file_ref in issue.mentioned_files[:10]:
            results = self.vector_store.search_by_text(query=file_ref.path, repo_id=repo_id, limit=5)
            for record in results:
                path = record.get("path", "")
                if file_ref.path in path or path in file_ref.path:
                    reasons = ["explicit file mention"]
                    if self._is_related_test(path, issue):
                        reasons.append("nearby test coverage")
                    units.append(
                        self._build_unit(
                            record,
                            issue,
                            score=0.92 if path == file_ref.path else 0.82,
                            match_type="explicit",
                            reasons=reasons,
                        )
                    )

        return units[:limit]

    def _build_unit(
        self,
        record: dict,
        issue: ProcessedIssue,
        score: float,
        match_type: str,
        reasons: list[str],
    ) -> RetrievedUnit:
        path = record.get("path", "")
        if self._is_related_test(path, issue) and "nearby test coverage" not in reasons:
            reasons.append("nearby test coverage")

        return RetrievedUnit(
            id=record.get("id", ""),
            path=path,
            name=record.get("name"),
            unit_type=record.get("unit_type", "file"),
            language=record.get("language", ""),
            start_line=record.get("start_line", 0),
            end_line=record.get("end_line", 0),
            signature=record.get("signature"),
            docstring=record.get("docstring"),
            code=record.get("code", "")[:700],
            asset_kind=record.get("asset_kind", AssetKind.CODE.value),
            score=max(score, 0.0),
            match_type=match_type,
            is_test=self._is_test_file(path),
            match_reasons=list(dict.fromkeys(reasons)),
        )

    def _combine_results(
        self,
        issue: ProcessedIssue,
        semantic: list[RetrievedUnit],
        keyword: list[RetrievedUnit],
        explicit: list[RetrievedUnit],
        limit: int,
    ) -> list[RetrievedUnit]:
        seen: dict[str, RetrievedUnit] = {}

        for source_name, units in (
            ("explicit", explicit),
            ("keyword", keyword),
            ("semantic", semantic),
        ):
            for unit in units:
                weighted_score = unit.score * self.WEIGHTS[source_name]
                weighted_score += self._evidence_boost(issue, unit)
                if unit.id not in seen:
                    unit.score = weighted_score
                    seen[unit.id] = unit
                else:
                    existing = seen[unit.id]
                    existing.score += weighted_score
                    existing.match_reasons = list(
                        dict.fromkeys(existing.match_reasons + unit.match_reasons)
                    )
                    if source_name == "explicit":
                        existing.match_type = "explicit"
                    elif source_name == "keyword" and existing.match_type == "semantic":
                        existing.match_type = "keyword"

        combined = list(seen.values())
        combined.sort(key=lambda unit: (unit.score, unit.is_test, unit.path), reverse=True)

        selected = []
        file_counts: dict[str, int] = {}
        seen_keys: set[tuple[str, str | None, int, int]] = set()
        for unit in combined:
            key = (unit.path, unit.name, unit.start_line, unit.end_line)
            if key in seen_keys:
                continue
            path_count = file_counts.get(unit.path, 0)
            if path_count >= 2 and not unit.is_test:
                continue
            selected.append(unit)
            seen_keys.add(key)
            file_counts[unit.path] = path_count + 1
            if len(selected) >= limit:
                break

        return selected

    def _evidence_boost(self, issue: ProcessedIssue, unit: RetrievedUnit) -> float:
        boost = 0.0
        if self._is_explicitly_mentioned(issue, unit.path):
            boost += 0.18
        if self._is_exact_symbol_match(issue, unit.name):
            boost += 0.14
        if unit.is_test and issue.issue_type in {IssueType.BUG, IssueType.TEST}:
            boost += 0.08
        if unit.asset_kind == AssetKind.DOCS.value and issue.issue_type != IssueType.DOCS:
            boost -= 0.10
        if unit.asset_kind in {AssetKind.CONFIG.value, AssetKind.WORKFLOW.value} and issue.issue_type == IssueType.BUG:
            boost -= 0.04
        if unit.docstring:
            boost += 0.02
        return boost

    def _is_test_file(self, path: str) -> bool:
        return "test" in path.lower()

    def _adjust_semantic_score(
        self,
        score: float,
        asset_kind: str,
        path: str,
        issue: ProcessedIssue,
    ) -> float:
        adjusted = score
        if asset_kind == AssetKind.CODE.value:
            return adjusted

        if self._is_explicitly_mentioned(issue, path):
            adjusted *= 1.08

        if asset_kind == AssetKind.DOCS.value and issue.issue_type != IssueType.DOCS:
            adjusted *= 0.55
        elif asset_kind in {AssetKind.CONFIG.value, AssetKind.WORKFLOW.value}:
            if issue.issue_type in {IssueType.DOCS, IssueType.UNKNOWN}:
                adjusted *= 0.78
            else:
                adjusted *= 0.88

        return adjusted

    def _is_explicitly_mentioned(self, issue: ProcessedIssue, path: str) -> bool:
        return any(file_ref.path in path or path in file_ref.path for file_ref in issue.mentioned_files)

    def _is_exact_symbol_match(self, issue: ProcessedIssue, name: Optional[str]) -> bool:
        if not name:
            return False
        return any(symbol.name == name for symbol in issue.mentioned_symbols)

    def _is_related_test(self, path: str, issue: ProcessedIssue) -> bool:
        if not self._is_test_file(path):
            return False
        referenced = [file_ref.path.rsplit("/", 1)[-1].split(".")[0] for file_ref in issue.mentioned_files]
        if any(ref and ref in path for ref in referenced):
            return True
        return any(symbol.name.lower() in path.lower() for symbol in issue.mentioned_symbols[:5])


__all__ = [
    "RetrievedUnit",
    "RetrievalResult",
    "HybridRetriever",
]
