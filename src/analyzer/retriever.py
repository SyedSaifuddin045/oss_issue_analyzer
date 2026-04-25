from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from src.analyzer.preprocessor import IssueType, ProcessedIssue
from src.indexer.parser import AssetKind, UnitType

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


@dataclass
class RetrievalResult:
    issue: ProcessedIssue
    units: list[RetrievedUnit] = field(default_factory=list)
    search_stats: dict = field(default_factory=dict)


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

    def search(
        self,
        issue: ProcessedIssue,
        repo_id: str,
        limit: int = 10,
    ) -> RetrievalResult:
        self._repo_id = repo_id
        
        semantic_results = self._semantic_search(issue, repo_id, limit * 2)
        keyword_results = self._keyword_search(issue, repo_id, limit)
        explicit_results = self._explicit_search(issue, repo_id, limit)
        
        combined = self._combine_results(
            semantic_results,
            keyword_results,
            explicit_results,
            limit,
        )
        
        search_stats = {
            "semantic_count": len(semantic_results),
            "keyword_count": len(keyword_results),
            "explicit_count": len(explicit_results),
        }

        return RetrievalResult(
            issue=issue,
            units=combined,
            search_stats=search_stats,
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
        for r in results:
            units.append(
                RetrievedUnit(
                    id=r.get("id", ""),
                    path=r.get("path", ""),
                    name=r.get("name"),
                    unit_type=r.get("unit_type", "file"),
                    language=r.get("language", ""),
                    start_line=r.get("start_line", 0),
                    end_line=r.get("end_line", 0),
                    signature=r.get("signature"),
                    docstring=r.get("docstring"),
                    code=r.get("code", "")[:500],
                    asset_kind=r.get("asset_kind", AssetKind.CODE.value),
                    score=self._adjust_semantic_score(
                        r.get("_score", 0.0),
                        r.get("asset_kind", AssetKind.CODE.value),
                        r.get("path", ""),
                        issue,
                    ),
                    match_type="semantic",
                    is_test=self._is_test_file(r.get("path", "")),
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
        
        for symbol in issue.mentioned_symbols[:10]:
            results = self.vector_store.search_by_text(
                query=symbol.name,
                repo_id=repo_id,
                limit=3,
            )
            for r in results:
                if r.get("name") == symbol.name:
                    units.append(
                        RetrievedUnit(
                            id=r.get("id", ""),
                            path=r.get("path", ""),
                            name=r.get("name"),
                            unit_type=r.get("unit_type", "file"),
                            language=r.get("language", ""),
                            start_line=r.get("start_line", 0),
                            end_line=r.get("end_line", 0),
                            signature=r.get("signature"),
                            docstring=r.get("docstring"),
                            code=r.get("code", "")[:500],
                            asset_kind=r.get("asset_kind", AssetKind.CODE.value),
                            score=0.7,
                            match_type="keyword",
                            is_test=self._is_test_file(r.get("path", "")),
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
            results = self.vector_store.search_by_text(
                query=file_ref.path,
                repo_id=repo_id,
                limit=3,
            )
            for r in results:
                if file_ref.path in r.get("path", ""):
                    units.append(
                        RetrievedUnit(
                            id=r.get("id", ""),
                            path=r.get("path", ""),
                            name=r.get("name"),
                            unit_type=r.get("unit_type", "file"),
                            language=r.get("language", ""),
                            start_line=r.get("start_line", 0),
                            end_line=r.get("end_line", 0),
                            signature=r.get("signature"),
                            docstring=r.get("docstring"),
                            code=r.get("code", "")[:500],
                            asset_kind=r.get("asset_kind", AssetKind.CODE.value),
                            score=0.9,
                            match_type="explicit",
                            is_test=self._is_test_file(r.get("path", "")),
                        )
                    )

        return units[:limit]

    def _combine_results(
        self,
        semantic: list[RetrievedUnit],
        keyword: list[RetrievedUnit],
        explicit: list[RetrievedUnit],
        limit: int,
    ) -> list[RetrievedUnit]:
        seen = {}
        
        for unit in explicit:
            if unit.id not in seen:
                unit.score = unit.score * self.WEIGHTS["explicit"]
                seen[unit.id] = unit
        
        for unit in keyword:
            if unit.id not in seen:
                unit.score = unit.score * self.WEIGHTS["keyword"]
                seen[unit.id] = unit
            else:
                seen[unit.id].score += unit.score * self.WEIGHTS["keyword"]
        
        for unit in semantic:
            if unit.id not in seen:
                unit.score = unit.score * self.WEIGHTS["semantic"]
                seen[unit.id] = unit
            else:
                seen[unit.id].score += unit.score * self.WEIGHTS["semantic"]

        combined = list(seen.values())
        combined.sort(key=lambda x: x.score, reverse=True)
        
        unique = []
        seen_paths = set()
        for unit in combined:
            if unit.path not in seen_paths:
                seen_paths.add(unit.path)
                unique.append(unit)

        return unique[:limit]

    def _is_test_file(self, path: str) -> bool:
        return "test" in path.lower()

    def _adjust_semantic_score(
        self,
        score: float,
        asset_kind: str,
        path: str,
        issue: ProcessedIssue,
    ) -> float:
        if asset_kind == AssetKind.CODE.value:
            return score

        if self._is_explicitly_mentioned(issue, path):
            return score * 1.1

        if asset_kind == AssetKind.DOCS.value and issue.issue_type != IssueType.DOCS:
            return score * 0.65

        if asset_kind in {AssetKind.CONFIG.value, AssetKind.WORKFLOW.value}:
            if issue.issue_type in {IssueType.DOCS, IssueType.UNKNOWN}:
                return score * 0.8
            return score * 0.9

        return score

    def _is_explicitly_mentioned(self, issue: ProcessedIssue, path: str) -> bool:
        return any(file_ref.path in path or path in file_ref.path for file_ref in issue.mentioned_files)


__all__ = [
    "RetrievedUnit",
    "RetrievalResult",
    "HybridRetriever",
]
