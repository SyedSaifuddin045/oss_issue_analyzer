from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.indexer.dependencies import DependencyProfile
from src.indexer.indexer import CodeIndexer, IndexerConfig, index_repository
from src.indexer.parser import AssetKind, ParsedUnit, UnitType
from src.indexer.storage import VectorStore


class FakeEmbedder:
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.5, 0.25] for _ in texts]


class FakeVectorStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.repos: dict[str, dict] = {}
        self.file_hashes: dict[tuple[str, str], str] = {}
        self.deleted_files: list[tuple[str, str]] = []
        self.added_payloads: list[tuple[list[ParsedUnit], str, dict[str, list[float]], str]] = []
        self.dependency_profiles: dict[str, DependencyProfile] = {}

    def get_repository(self, repo_id: str):
        return self.repos.get(repo_id)

    def validate_repo_compatibility(self, repo_id: str):
        return True, None

    def add_repository(self, repo) -> None:
        self.repos[repo.id] = repo.model_dump()

    def compute_file_hash(self, file_path: str, content: str) -> str:
        return f"hash:{file_path}:{len(content)}"

    def get_file_hash(self, repo_id: str, file_path: str):
        return self.file_hashes.get((repo_id, file_path))

    def delete_by_file(self, repo_id: str, file_path: str) -> int:
        self.deleted_files.append((repo_id, file_path))
        self.file_hashes.pop((repo_id, file_path), None)
        return 1

    def add_code_units(self, units: list[ParsedUnit], repo_id: str, embeddings: dict[str, list[float]], file_hash: str) -> int:
        self.added_payloads.append((units, repo_id, embeddings, file_hash))
        self.file_hashes[(repo_id, units[-1].path)] = file_hash
        return len(units)

    def get_stats(self, repo_id: str) -> dict:
        return {
            "files": 1,
            "classes": 0,
            "functions": 1,
            "methods": 0,
            "total_units": 2,
            "by_type": {"file": 1, "function": 1},
        }

    def add_dependency_profile(self, profile: DependencyProfile) -> None:
        self.dependency_profiles[profile.repo_id] = profile

    def get_dependency_profile(self, repo_id: str) -> DependencyProfile | None:
        return self.dependency_profiles.get(repo_id)


class FakeParser:
    def parse_file(self, source: str, file_path: str, repo_id: str) -> ParsedUnit:
        child = ParsedUnit(
            id=f"{repo_id}:{file_path}:2-3:hello",
            repo_id=repo_id,
            unit_type=UnitType.FUNCTION,
            path=file_path,
            language="python",
            start_line=2,
            end_line=3,
            signature="def hello():",
            docstring=None,
            code="def hello():\n    return 'hi'\n",
            name="hello",
        )
        return ParsedUnit(
            id=f"{repo_id}:{file_path}:1-3:file",
            repo_id=repo_id,
            unit_type=UnitType.FILE,
            path=file_path,
            language="python",
            start_line=1,
            end_line=3,
            code=source,
            name=file_path,
            children=[child],
        )


class IndexerTests(unittest.TestCase):
    def test_index_file_replaces_stale_units(self) -> None:
        import src.indexer.indexer as indexer_module
        import src.indexer.storage as storage_module

        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            fake_store = FakeVectorStore(str(tmp_path / "index.lance"))
            original_vector_store = storage_module.VectorStore
            original_parser = indexer_module.get_parser_for_file
            original_get_embedder = indexer_module.get_embedder

            storage_module.VectorStore = lambda db_path: fake_store
            indexer_module.get_parser_for_file = lambda _: FakeParser()
            indexer_module.get_embedder = lambda model, device: FakeEmbedder()
            self.addCleanup(setattr, storage_module, "VectorStore", original_vector_store)
            self.addCleanup(setattr, indexer_module, "get_parser_for_file", original_parser)
            self.addCleanup(setattr, indexer_module, "get_embedder", original_get_embedder)

            repo_path = tmp_path / "repo"
            repo_path.mkdir()
            source_file = repo_path / "app.py"
            source_file.write_text("x = 1\n\ndef hello():\n    return 'hi'\n", encoding="utf-8")

            indexer = CodeIndexer(
                IndexerConfig(repo_path=str(repo_path), db_path=str(tmp_path / "index.lance"))
            )
            repo_id = indexer._get_or_create_repo(repo_path)
            indexer.repo_id = repo_id
            fake_store.file_hashes[(repo_id, "app.py")] = "old-hash"

            units_added = indexer._index_file(source_file, repo_path)

            self.assertEqual(units_added, 2)
            self.assertEqual(fake_store.deleted_files, [(repo_id, "app.py")])
            self.assertTrue(fake_store.added_payloads[0][3].startswith("hash:app.py:"))

    def test_discover_files_in_mixed_mode_includes_curated_non_code_assets(self) -> None:
        import src.indexer.indexer as indexer_module
        import src.indexer.storage as storage_module

        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            fake_store = FakeVectorStore(str(tmp_path / "index.lance"))
            original_vector_store = storage_module.VectorStore
            storage_module.VectorStore = lambda db_path: fake_store
            self.addCleanup(setattr, storage_module, "VectorStore", original_vector_store)

            repo_path = tmp_path / "repo"
            (repo_path / "docs").mkdir(parents=True)
            (repo_path / ".github" / "workflows").mkdir(parents=True)
            (repo_path / "app.py").write_text("print('hello')\n", encoding="utf-8")
            (repo_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
            (repo_path / "README.md").write_text("# Demo\n", encoding="utf-8")
            (repo_path / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
            (repo_path / ".github" / "workflows" / "ci.yml").write_text("name: CI\n", encoding="utf-8")
            (repo_path / "notes.txt").write_text("ignore me\n", encoding="utf-8")

            indexer = CodeIndexer(
                IndexerConfig(repo_path=str(repo_path), db_path=str(tmp_path / "index.lance"))
            )

            discovered = {
                path.relative_to(repo_path).as_posix(): asset_kind
                for path, asset_kind in indexer._discover_files(repo_path)
            }

            self.assertEqual(discovered["app.py"], AssetKind.CODE)
            self.assertEqual(discovered["pyproject.toml"], AssetKind.DEPENDENCY)
            self.assertEqual(discovered["README.md"], AssetKind.DOCS)
            self.assertEqual(discovered["docs/guide.md"], AssetKind.DOCS)
            self.assertEqual(discovered[".github/workflows/ci.yml"], AssetKind.WORKFLOW)
            self.assertNotIn("notes.txt", discovered)

    def test_index_file_builds_non_code_unit_and_honors_code_only_mode(self) -> None:
        import src.indexer.indexer as indexer_module
        import src.indexer.storage as storage_module

        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            fake_store = FakeVectorStore(str(tmp_path / "index.lance"))
            original_vector_store = storage_module.VectorStore
            original_get_embedder = indexer_module.get_embedder

            storage_module.VectorStore = lambda db_path: fake_store
            indexer_module.get_embedder = lambda model, device: FakeEmbedder()
            self.addCleanup(setattr, storage_module, "VectorStore", original_vector_store)
            self.addCleanup(setattr, indexer_module, "get_embedder", original_get_embedder)

            repo_path = tmp_path / "repo"
            repo_path.mkdir()
            config_file = repo_path / "pyproject.toml"
            config_file.write_text("[project]\nname = 'demo'\n", encoding="utf-8")

            mixed_indexer = CodeIndexer(
                IndexerConfig(repo_path=str(repo_path), db_path=str(tmp_path / "index.lance"))
            )
            repo_id = mixed_indexer._get_or_create_repo(repo_path)
            mixed_indexer.repo_id = repo_id

            units_added = mixed_indexer._index_file(config_file, repo_path, AssetKind.DEPENDENCY)

            self.assertEqual(units_added, 1)
            added_unit = fake_store.added_payloads[0][0][0]
            self.assertEqual(added_unit.asset_kind, AssetKind.DEPENDENCY)
            self.assertEqual(added_unit.unit_type, UnitType.CONFIG)
            self.assertEqual(added_unit.name, "pyproject.toml")

            code_only_indexer = CodeIndexer(
                IndexerConfig(
                    repo_path=str(repo_path),
                    db_path=str(tmp_path / "index.lance"),
                    index_mode="code-only",
                )
            )
            discovered = {
                path.relative_to(repo_path).as_posix()
                for path, _asset_kind in code_only_indexer._discover_files(repo_path)
            }
            self.assertNotIn("pyproject.toml", discovered)

            dependency_profile = code_only_indexer._analyze_dependencies(repo_path)
            self.assertEqual(dependency_profile.manifest_count, 1)
            self.assertIn("python", dependency_profile.ecosystems)

    def test_parser_registry_supports_expanded_languages(self) -> None:
        import src.indexer.parser as parser_module

        expected = {
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
            ".c": "c",
            ".h": "c",
            ".cc": "cpp",
            ".cpp": "cpp",
            ".cxx": "cpp",
            ".hpp": "cpp",
            ".hh": "cpp",
            ".hxx": "cpp",
        }

        for extension, language in expected.items():
            parser = parser_module.get_parser_for_file(f"demo{extension}")
            self.assertIsNotNone(parser)
            self.assertEqual(parser.language, language)

    def test_index_repository_calls_run(self) -> None:
        captured: dict[str, str] = {}
        original_init = CodeIndexer.__init__
        original_run = CodeIndexer.run

        def fake_init(self, config):
            self.config = config

        def fake_run(self):
            captured["repo_path"] = self.config.repo_path
            return {"repo_id": "abc123"}

        try:
            CodeIndexer.__init__ = fake_init
            CodeIndexer.run = fake_run
            result = index_repository("/tmp/example", db_path="/tmp/index.lance", embedder="minilm")
        finally:
            CodeIndexer.__init__ = original_init
            CodeIndexer.run = original_run

        self.assertEqual(result, {"repo_id": "abc123"})
        self.assertEqual(captured["repo_path"], "/tmp/example")

    def test_vector_store_rejects_outdated_repo_schema(self) -> None:
        store = VectorStore.__new__(VectorStore)
        store.is_compatible_schema = lambda: True
        store.get_repository = lambda repo_id: {
            "id": repo_id,
            "schema_version": 2,
            "index_mode": "mixed",
        }

        is_compatible, error = VectorStore.validate_repo_compatibility(store, "repo-1")

        self.assertFalse(is_compatible)
        self.assertIn("Repository index is outdated", error)


if __name__ == "__main__":
    unittest.main()
