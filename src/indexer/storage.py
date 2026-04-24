from __future__ import annotations
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import pyarrow as pa
import lancedb
from lancedb.pydantic import LanceModel

from src.indexer.parser import ParsedUnit


class CodeUnit(LanceModel):
    id: str
    repo_id: str
    unit_type: str
    path: str
    language: str
    start_line: int
    end_line: int
    signature: Optional[str] = None
    docstring: Optional[str] = None
    code: str
    file_hash: str
    indexed_at: datetime = field(default_factory=datetime.utcnow)
    name: Optional[str] = None
    parent_name: Optional[str] = None

    @staticmethod
    def get_schema() -> pa.Schema:
        return get_code_unit_schema()


def get_code_unit_schema() -> pa.Schema:
    return pa.schema([
        pa.field("id", pa.string()),
        pa.field("repo_id", pa.string()),
        pa.field("unit_type", pa.string()),
        pa.field("path", pa.string()),
        pa.field("language", pa.string()),
        pa.field("start_line", pa.int64()),
        pa.field("end_line", pa.int64()),
        pa.field("signature", pa.string()),
        pa.field("docstring", pa.string()),
        pa.field("code", pa.string()),
        pa.field("file_hash", pa.string()),
        pa.field("indexed_at", pa.timestamp("us")),
        pa.field("name", pa.string()),
        pa.field("parent_name", pa.string()),
        pa.field("vector", pa.list_(pa.float32())),
    ])


@dataclass
class ComplexityMetrics:
    cyclomatic_complexity: int = 0
    lines_of_code: int = 0
    cognitive_complexity: int = 0
    fan_in: int = 0
    fan_out: int = 0


@dataclass
class ContributorSignals:
    is_well_documented: bool = False
    has_type_hints: bool = False
    has_tests: bool = False
    is_isolated: bool = False
    has_clear_naming: bool = False


class CodeUnit(LanceModel):
    id: str
    repo_id: str
    unit_type: str
    path: str
    language: str
    start_line: int
    end_line: int
    signature: Optional[str] = None
    docstring: Optional[str] = None
    code: str
    file_hash: str
    indexed_at: datetime = field(default_factory=datetime.utcnow)
    name: Optional[str] = None
    parent_name: Optional[str] = None


class Repository(LanceModel):
    id: str
    name: str
    path: str
    language: str
    indexed_at: datetime = field(default_factory=datetime.utcnow)


class VectorStore:
    def __init__(self, db_path: str = "./.data/index.lance"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = lancedb.connect(str(self.db_path))

    def _get_code_unit_table(self) -> lancedb.table.Table:
        if "code_units" not in self.db.table_names():
            return self.db.create_table("code_units", schema=get_code_unit_schema(), mode="overwrite")
        return self.db.open_table("code_units")

    def _get_repo_table(self) -> lancedb.table.Table:
        if "repositories" not in self.db.table_names():
            return self.db.create_table("repositories", schema=Repository, mode="overwrite")
        return self.db.open_table("repositories")

    @staticmethod
    def compute_file_hash(file_path: str, content: str) -> str:
        hasher = hashlib.sha256()
        hasher.update(file_path.encode())
        hasher.update(content.encode())
        return hasher.hexdigest()[:16]

    def add_code_units(
        self,
        units: list[ParsedUnit],
        repo_id: str,
        embeddings: dict[str, list[float]],
    ) -> int:
        table = self._get_code_unit_table()
        records = []
        for unit in units:
            embedding = embeddings.get(unit.id, [0.0] * 768)
            record = {
                "id": unit.id,
                "repo_id": repo_id,
                "unit_type": unit.unit_type.value,
                "path": unit.path,
                "language": unit.language,
                "start_line": unit.start_line,
                "end_line": unit.end_line,
                "signature": unit.signature,
                "docstring": unit.docstring,
                "code": unit.code[:10000],
                "file_hash": self.compute_file_hash(unit.path, unit.code),
                "indexed_at": datetime.utcnow(),
                "name": unit.name,
                "parent_name": unit.parent_name,
                "vector": embedding,
            }
            records.append(record)
        if records:
            table.add(records)
        return len(records)

    def search(
        self,
        query: str,
        query_embedding: list[float],
        repo_id: Optional[str] = None,
        unit_type: Optional[str] = None,
        limit: int = 10,
    ) -> list[dict]:
        try:
            table = self._get_code_unit_table()
            results = table.search(query_embedding, vector_column_name="vector").limit(limit * 2).to_arrow().to_pylist()
            filtered = self._filter_results(results, repo_id, unit_type)
            return filtered[:limit]
        except Exception:
            return []

    def search_by_text(
        self,
        query: str,
        repo_id: Optional[str] = None,
        unit_type: Optional[str] = None,
        limit: int = 10,
    ) -> list[dict]:
        all_units = self._get_code_unit_table().to_arrow().to_pylist()
        filtered = self._filter_results(all_units, repo_id, unit_type)
        return filtered[:limit]

    def _filter_results(
        self, results: list[dict], repo_id: Optional[str] = None, unit_type: Optional[str] = None
    ) -> list[dict]:
        filtered = results
        if repo_id:
            filtered = [r for r in filtered if r.get("repo_id") == repo_id]
        if unit_type:
            filtered = [r for r in filtered if r.get("unit_type") == unit_type]
        return filtered

    def get_units_by_file(self, repo_id: str, file_path: str) -> list[dict]:
        all_units = self._get_code_unit_table().to_arrow().to_pylist()
        return [u for u in all_units if u.get("repo_id") == repo_id and u.get("path") == file_path]

    def get_file_hash(self, repo_id: str, file_path: str) -> Optional[str]:
        units = self.get_units_by_file(repo_id, file_path)
        for u in units:
            if u.get("unit_type") == "file":
                return u.get("file_hash")
        return None

    def delete_by_repo(self, repo_id: str) -> int:
        table = self._get_code_unit_table()
        all_units = table.to_list()
        to_delete = [u for u in all_units if u.get("repo_id") == repo_id]
        ids_to_delete = [u.get("id") for u in to_delete if u.get("id")]
        for id_val in ids_to_delete:
            table.delete(f"id = '{id_val}'")
        return len(ids_to_delete)

    def list_repos(self) -> list[dict]:
        table = self._get_repo_table()
        return table.to_list()

    def add_repository(self, repo: Repository) -> None:
        table = self._get_repo_table()
        table.add([repo.model_dump()])

    def get_repository(self, repo_id: str) -> Optional[dict]:
        table = self._get_repo_table()
        all_repos = table.to_arrow().to_pylist()
        for r in all_repos:
            if r.get("id") == repo_id:
                return r
        return None

    def get_stats(self, repo_id: str) -> dict:
        table = self._get_code_unit_table()
        try:
            import pyarrow as pa
            all_units = table.to_arrow().to_pylist()
        except Exception:
            all_units = []
        
        by_type = {}
        for unit in all_units:
            if unit.get("repo_id") == repo_id:
                ut = unit.get("unit_type", "unknown")
                by_type[ut] = by_type.get(ut, 0) + 1
        return {
            "total_units": sum(by_type.values()),
            "by_type": by_type,
            "files": by_type.get("file", 0),
            "functions": by_type.get("function", 0),
            "classes": by_type.get("class", 0),
            "methods": by_type.get("method", 0),
        }


def get_index(db_path: str = "./.data/index.lance") -> VectorStore:
    return VectorStore(db_path)


CodeIndex = VectorStore


__all__ = [
    "CodeUnit",
    "Repository",
    "VectorStore",
    "CodeIndex",
    "ComplexityMetrics",
    "ContributorSignals",
    "get_index",
]