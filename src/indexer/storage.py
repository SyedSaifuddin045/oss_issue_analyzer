from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import lancedb
import pyarrow as pa
from lancedb.pydantic import LanceModel

from src.indexer.parser import ParsedUnit

INDEX_SCHEMA_VERSION = 2


def get_code_unit_schema(default_vector_size: int = 768) -> pa.Schema:
    return pa.schema(
        [
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
            pa.field("asset_kind", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), default_vector_size)),
        ]
    )


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
    signature: str | None = None
    docstring: str | None = None
    code: str
    file_hash: str
    indexed_at: datetime = field(default_factory=datetime.utcnow)
    name: str | None = None
    parent_name: str | None = None
    asset_kind: str = "code"
    vector: list[float]

    @staticmethod
    def get_schema() -> pa.Schema:
        return get_code_unit_schema()


class Repository(LanceModel):
    id: str
    name: str
    path: str
    language: str
    schema_version: int = INDEX_SCHEMA_VERSION
    index_mode: str = "mixed"
    indexed_at: datetime = field(default_factory=datetime.utcnow)


class VectorStore:
    def __init__(self, db_path: str = ".oss-index/index.lance", vector_size: int = 768):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = lancedb.connect(str(self.db_path))
        self.vector_size = vector_size

    def _get_code_unit_table(self):
        if "code_units" not in self.db.table_names():
            return self.db.create_table(
                "code_units",
                schema=get_code_unit_schema(self.vector_size),
                mode="overwrite",
            )
        return self.db.open_table("code_units")

    def _get_repo_table(self):
        if "repositories" not in self.db.table_names():
            return self.db.create_table("repositories", schema=Repository, mode="overwrite")
        return self.db.open_table("repositories")

    @staticmethod
    def compute_file_hash(file_path: str, content: str) -> str:
        hasher = hashlib.sha256()
        hasher.update(file_path.encode("utf-8"))
        hasher.update(content.encode("utf-8"))
        return hasher.hexdigest()[:16]

    def add_code_units(
        self,
        units: list[ParsedUnit],
        repo_id: str,
        embeddings: dict[str, list[float]],
        file_hash: str,
    ) -> int:
        table = self._get_code_unit_table()
        records = []
        for unit in units:
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
                "file_hash": file_hash,
                "indexed_at": datetime.utcnow(),
                "name": unit.name or None,
                "parent_name": unit.parent_name,
                "asset_kind": unit.asset_kind.value,
                "vector": self._normalize_embedding(embeddings.get(unit.id)),
            }
            records.append(record)

        if records:
            table.add(records)
        return len(records)

    def search(
        self,
        query: str,
        query_embedding: list[float],
        repo_id: str | None = None,
        unit_type: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        try:
            table = self._get_code_unit_table()
            results = (
                table.search(query_embedding, vector_column_name="vector")
                .limit(limit * 2)
                .to_arrow()
                .to_pylist()
            )
        except Exception:
            return []

        return self._filter_results(results, repo_id=repo_id, unit_type=unit_type)[:limit]

    def search_by_text(
        self,
        query: str,
        repo_id: str | None = None,
        unit_type: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        query_lower = query.strip().lower()
        if not query_lower:
            return []

        all_units = self._get_code_unit_table().to_arrow().to_pylist()
        filtered = self._filter_results(all_units, repo_id=repo_id, unit_type=unit_type)
        ranked = sorted(
            (
                record
                for record in filtered
                if self._matches_text_query(record, query_lower)
            ),
            key=lambda record: self._text_match_rank(record, query_lower),
            reverse=True,
        )
        return ranked[:limit]

    def _filter_results(
        self,
        results: list[dict],
        repo_id: str | None = None,
        unit_type: str | None = None,
    ) -> list[dict]:
        filtered = results
        if repo_id:
            filtered = [record for record in filtered if record.get("repo_id") == repo_id]
        if unit_type:
            filtered = [record for record in filtered if record.get("unit_type") == unit_type]
        return filtered

    def get_units_by_file(self, repo_id: str, file_path: str) -> list[dict]:
        all_units = self._get_code_unit_table().to_arrow().to_pylist()
        return [
            unit
            for unit in all_units
            if unit.get("repo_id") == repo_id and unit.get("path") == file_path
        ]

    def get_file_hash(self, repo_id: str, file_path: str) -> str | None:
        units = self.get_units_by_file(repo_id, file_path)
        for unit in units:
            if unit.get("unit_type") == "file":
                return unit.get("file_hash")
        return None

    def delete_by_file(self, repo_id: str, file_path: str) -> int:
        records = self.get_units_by_file(repo_id, file_path)
        ids = [record["id"] for record in records if record.get("id")]
        return self._delete_records_by_ids(ids)

    def delete_by_repo(self, repo_id: str) -> int:
        table = self._get_code_unit_table()
        records = table.to_arrow().to_pylist()
        ids = [record["id"] for record in records if record.get("repo_id") == repo_id]
        deleted = self._delete_records_by_ids(ids)
        self.delete_repository(repo_id)
        return deleted

    def list_repos(self) -> list[dict]:
        return self._get_repo_table().to_arrow().to_pylist()

    def add_repository(self, repo: Repository) -> None:
        table = self._get_repo_table()
        existing = self.get_repository(repo.id)
        if existing:
            table.delete(f"id = '{self._escape(repo.id)}'")
        table.add([repo.model_dump()])

    def delete_repository(self, repo_id: str) -> int:
        table = self._get_repo_table()
        existing = self.get_repository(repo_id)
        if not existing:
            return 0
        table.delete(f"id = '{self._escape(repo_id)}'")
        return 1

    def get_repository(self, repo_id: str) -> dict | None:
        repos = self._get_repo_table().to_arrow().to_pylist()
        for repo in repos:
            if repo.get("id") == repo_id:
                return repo
        return None

    def is_compatible_schema(self) -> bool:
        table_names = set(self.db.table_names())
        if "code_units" in table_names:
            code_fields = set(self._get_code_unit_table().schema.names)
            if "asset_kind" not in code_fields:
                return False
        if "repositories" in table_names:
            repo_fields = set(self._get_repo_table().schema.names)
            if "schema_version" not in repo_fields or "index_mode" not in repo_fields:
                return False
        return True

    def validate_repo_compatibility(self, repo_id: str) -> tuple[bool, str | None]:
        if not self.is_compatible_schema():
            return False, (
                "Index schema is outdated. Re-run 'oss-issue-analyzer index <repo_path> --force' "
                "to rebuild the index."
            )

        repo = self.get_repository(repo_id)
        if not repo:
            return True, None

        schema_version = repo.get("schema_version")
        if schema_version != INDEX_SCHEMA_VERSION:
            return False, (
                "Repository index is outdated. Re-run 'oss-issue-analyzer index <repo_path> --force' "
                "to rebuild the index."
            )
        return True, None

    def reset(self) -> None:
        if self.db_path.exists():
            shutil.rmtree(self.db_path)
        self.db = lancedb.connect(str(self.db_path))

    def get_stats(self, repo_id: str) -> dict:
        try:
            all_units = self._get_code_unit_table().to_arrow().to_pylist()
        except Exception:
            all_units = []

        by_type: dict[str, int] = {}
        for unit in all_units:
            if unit.get("repo_id") != repo_id:
                continue
            unit_type = unit.get("unit_type", "unknown")
            by_type[unit_type] = by_type.get(unit_type, 0) + 1

        return {
            "total_units": sum(by_type.values()),
            "by_type": by_type,
            "files": by_type.get("file", 0),
            "functions": by_type.get("function", 0),
            "classes": by_type.get("class", 0),
            "methods": by_type.get("method", 0),
        }

    def _delete_records_by_ids(self, ids: list[str]) -> int:
        table = self._get_code_unit_table()
        for unit_id in ids:
            table.delete(f"id = '{self._escape(unit_id)}'")
        return len(ids)

    def _matches_text_query(self, record: dict, query: str) -> bool:
        fields = (
            record.get("path", ""),
            record.get("name", ""),
            record.get("signature", ""),
            record.get("docstring", ""),
            record.get("code", ""),
        )
        return any(query in str(value).lower() for value in fields if value is not None)

    def _text_match_rank(self, record: dict, query: str) -> tuple[int, int, int]:
        path = str(record.get("path", "")).lower()
        name = str(record.get("name", "")).lower()
        signature = str(record.get("signature", "")).lower()
        code = str(record.get("code", "")).lower()
        return (
            int(path == query or name == query),
            int(query in path or query in name or query in signature),
            int(query in code),
        )

    def _normalize_embedding(self, embedding: list[float] | None) -> list[float]:
        if embedding is None:
            return [0.0] * self.vector_size
        vector = [float(value) for value in embedding[: self.vector_size]]
        if len(vector) < self.vector_size:
            vector.extend([0.0] * (self.vector_size - len(vector)))
        return vector

    @staticmethod
    def _escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace("'", "\\'")


def get_index(db_path: str = "./.data/index.lance") -> VectorStore:
    return VectorStore(db_path)


CodeIndex = VectorStore


__all__ = [
    "INDEX_SCHEMA_VERSION",
    "CodeUnit",
    "Repository",
    "VectorStore",
    "CodeIndex",
    "ComplexityMetrics",
    "ContributorSignals",
    "get_index",
]
