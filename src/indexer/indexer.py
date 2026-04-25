from __future__ import annotations
import hashlib
from fnmatch import fnmatch
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Literal, Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from src.indexer.parser import AssetKind, ParsedUnit, UnitType, get_parser_for_file, MultiLanguageParser
from src.indexer.storage import INDEX_SCHEMA_VERSION, Repository

if TYPE_CHECKING:
    from src.indexer.embedder import Embedder


def get_embedder(model: str, device: Optional[str] = None):
    from src.indexer.embedder import get_embedder as load_embedder

    return load_embedder(model, device)


@dataclass
class IndexerConfig:
    repo_path: str
    db_path: str = ".data/index.lance"
    embedder_model: str = "minilm"
    index_mode: Literal["mixed", "code-only"] = "mixed"
    device: Optional[str] = None
    batch_size: int = 32
    max_text_file_bytes: int = 128 * 1024
    skip_patterns: list[str] = field(default_factory=lambda: [
        "__pycache__", ".git", "node_modules", "venv", ".venv", "build", "dist", ".tox", ".pytest_cache", "*.pyc", ".mypy_cache", ".ruff_cache"
    ])
    non_code_patterns: list[str] = field(default_factory=lambda: [
        "*.json",
        "*.toml",
        "*.yaml",
        "*.yml",
        "*.ini",
        "*.cfg",
        "*.conf",
        "*.env.example",
        "*.env.sample",
        "Dockerfile*",
        "docker-compose*",
        "README*",
        "docs/**/*.md",
        ".github/workflows/*",
    ])


class CodeIndexer:
    def __init__(self, config: IndexerConfig):
        self.config = config
        self.console = Console()
        from src.indexer.storage import VectorStore
        self.vector_store = VectorStore(config.db_path)
        self.embedder: Optional[Embedder] = None
        self.repo_id: Optional[str] = None

    def run(self) -> dict:
        repo_path = Path(self.config.repo_path).resolve()
        if not repo_path.exists():
            raise ValueError(f"Path does not exist: {repo_path}")
        if not repo_path.is_dir():
            raise ValueError(f"Repository path must be a directory: {repo_path}")

        self.console.print(f"[bold blue]Indexing repository:[/bold blue] {repo_path}")

        repo_id = self._make_repo_id(repo_path)
        is_compatible, error = self.vector_store.validate_repo_compatibility(repo_id)
        if not is_compatible:
            raise ValueError(error)

        self.repo_id = self._get_or_create_repo(repo_path)

        files = self._discover_files(repo_path)
        self.console.print(f"Found [bold]{len(files)}[/bold] files to index")

        total_units = 0
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=self.console,
        ) as progress:
            task = progress.add_task("Indexing...", total=len(files))

            for file_path, asset_kind in files:
                try:
                    units_added = self._index_file(file_path, repo_path, asset_kind)
                    total_units += units_added
                except Exception as e:
                    self.console.print(f"[yellow]Warning: Failed to index {file_path}: {e}[/yellow]")
                progress.update(task, advance=1)

        stats = self.vector_store.get_stats(self.repo_id)
        self.console.print(f"[bold green]Indexed {total_units} units![/bold green]")

        return {
            "repo_id": self.repo_id,
            "repo_path": str(repo_path),
            "index_mode": self.config.index_mode,
            "files_indexed": len(files),
            "units_indexed": total_units,
            "stats": stats,
        }

    def _get_or_create_repo(self, repo_path: Path) -> str:
        repo_id = self._make_repo_id(repo_path)

        detected_lang = self._detect_language(repo_path)

        repo = Repository(
            id=repo_id,
            name=repo_path.name,
            path=str(repo_path),
            language=detected_lang,
            schema_version=INDEX_SCHEMA_VERSION,
            index_mode=self.config.index_mode,
            indexed_at=datetime.utcnow(),
        )
        self.vector_store.add_repository(repo)
        self.console.print(f"Prepared repository: {repo_id} (language: {detected_lang})")

        return repo_id

    def _make_repo_id(self, repo_path: Path) -> str:
        return hashlib.sha256(str(repo_path).encode()).hexdigest()[:16]

    def _detect_language(self, repo_path: Path) -> str:
        extensions: dict[str, int] = {}
        
        for file_path in repo_path.rglob("*"):
            if file_path.is_file() and not self._should_skip(file_path):
                ext = file_path.suffix
                if ext:
                    extensions[ext] = extensions.get(ext, 0) + 1
        
        lang_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".jsx": "javascript",
            ".tsx": "typescript",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
        }
        
        for ext, count in sorted(extensions.items(), key=lambda x: -x[1])[:5]:
            if ext in lang_map:
                return lang_map[ext]
        
        return "python"

    def _discover_files(self, repo_path: Path) -> list[tuple[Path, AssetKind]]:
        files: list[tuple[Path, AssetKind]] = []
        for file_path in repo_path.rglob("*"):
            if file_path.is_file() and not self._should_skip(file_path):
                relative_path = file_path.relative_to(repo_path).as_posix()
                if file_path.suffix in MultiLanguageParser.supported_extensions():
                    files.append((file_path, AssetKind.CODE))
                    continue
                if self.config.index_mode == "mixed":
                    asset_kind = self._classify_non_code_asset(relative_path)
                    if asset_kind is not None:
                        files.append((file_path, asset_kind))
        return files

    def _should_skip(self, path: Path) -> bool:
        path_str = str(path)
        path_parts = set(path.parts)
        for pattern in self.config.skip_patterns:
            if pattern.startswith("*"):
                if path_str.endswith(pattern[1:]):
                    return True
            elif "/" in pattern or "\\" in pattern:
                if pattern in path_str:
                    return True
            elif pattern in path_parts:
                return True
        return False

    def _index_file(
        self,
        file_path: Path,
        repo_root: Path,
        asset_kind: AssetKind = AssetKind.CODE,
    ) -> int:
        relative_path = str(file_path.relative_to(repo_root))

        content = self._read_text_content(file_path)
        if content is None:
            return 0

        file_hash = self.vector_store.compute_file_hash(relative_path, content)
        existing_hash = self.vector_store.get_file_hash(self.repo_id, relative_path)
        if existing_hash == file_hash:
            return 0
        if existing_hash is not None:
            self.vector_store.delete_by_file(self.repo_id, relative_path)

        all_units = self._build_units(file_path, relative_path, content, asset_kind)
        if not all_units:
            return 0

        texts_to_embed = []
        embedded_unit_map = {}
        for unit in all_units:
            text = self._build_embedding_text(unit)
            if text:
                texts_to_embed.append(text)
                embedded_unit_map[unit.id] = unit

        if not texts_to_embed:
            return 0

        self._ensure_embedder_loaded()

        try:
            embeddings_list = self.embedder.embed_batch(texts_to_embed)
        except Exception as e:
            self.console.print(f"[dim]Embedding error: {file_path}: {e}[/dim]")
            return 0

        embeddings_map = {}
        for i, unit_id in enumerate(embedded_unit_map):
            if i < len(embeddings_list):
                embeddings_map[unit_id] = embeddings_list[i]

        try:
            return self.vector_store.add_code_units(
                all_units,
                self.repo_id,
                embeddings_map,
                file_hash=file_hash,
            )
        except Exception as e:
            self.console.print(f"[dim]Storage error: {file_path}: {e}[/dim]")
            return 0

    def _flatten_units(self, unit: ParsedUnit) -> list[ParsedUnit]:
        result = []
        for child in unit.children:
            result.append(child)
            result.extend(self._flatten_units(child))
        return result

    def _build_units(
        self,
        file_path: Path,
        relative_path: str,
        content: str,
        asset_kind: AssetKind,
    ) -> list[ParsedUnit]:
        if asset_kind == AssetKind.CODE:
            parser = get_parser_for_file(str(file_path))
            if not parser:
                return []
            try:
                parsed = parser.parse_file(content, relative_path, self.repo_id)
            except Exception as e:
                self.console.print(f"[dim]Parse error: {file_path}: {e}[/dim]")
                return []

            all_units = self._flatten_units(parsed)
            all_units.append(parsed)
            return all_units

        unit_type = UnitType.DOCUMENT if asset_kind == AssetKind.DOCS else UnitType.CONFIG
        return [
            ParsedUnit(
                id=f"{self.repo_id}:{relative_path}:1-{max(content.count(chr(10)) + 1, 1)}:{asset_kind.value}",
                repo_id=self.repo_id,
                unit_type=unit_type,
                path=relative_path,
                language="text",
                start_line=1,
                end_line=max(content.count("\n") + 1, 1),
                signature=None,
                docstring=None,
                code=content,
                name=relative_path,
                asset_kind=asset_kind,
            )
        ]

    def _build_embedding_text(self, unit: ParsedUnit) -> str:
        if unit.asset_kind == AssetKind.CODE:
            return unit.code[:2000]
        normalized_path = unit.path.replace("/", " ")
        return f"{unit.asset_kind.value} {normalized_path}\n{unit.code[:4000]}".strip()

    def _read_text_content(self, file_path: Path) -> str | None:
        try:
            if file_path.stat().st_size > self.config.max_text_file_bytes:
                return None
        except OSError:
            return None

        try:
            return file_path.read_text(encoding="utf-8", errors="strict")
        except UnicodeDecodeError:
            return None
        except OSError:
            return None

    def _classify_non_code_asset(self, relative_path: str) -> AssetKind | None:
        if relative_path.startswith(".github/workflows/"):
            return AssetKind.WORKFLOW
        if relative_path.startswith("docs/") and relative_path.endswith(".md"):
            return AssetKind.DOCS
        if Path(relative_path).name.lower().startswith("readme"):
            return AssetKind.DOCS

        posix_path = PurePosixPath(relative_path)
        for pattern in self.config.non_code_patterns:
            if posix_path.match(pattern) or fnmatch(relative_path, pattern):
                return AssetKind.CONFIG
        return None

    def _ensure_embedder_loaded(self) -> None:
        if self.embedder is None:
            self.embedder = get_embedder(self.config.embedder_model, self.config.device)


def index_repository(
    repo_path: str,
    db_path: str = "./data/index.lance",
    embedder: str = "minilm",
) -> dict:
    config = IndexerConfig(
        repo_path=repo_path,
        db_path=db_path,
        embedder_model=embedder,
    )
    indexer = CodeIndexer(config)
    return indexer.run()


__all__ = [
    "IndexerConfig",
    "CodeIndexer",
    "index_repository",
]
