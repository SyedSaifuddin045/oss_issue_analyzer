from __future__ import annotations
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from src.indexer.parser import ParsedUnit, get_parser_for_file, MultiLanguageParser
from src.indexer.embedder import Embedder, get_embedder
from src.indexer.storage import Repository


@dataclass
class IndexerConfig:
    repo_path: str
    db_path: str = ".data/index.lance"
    embedder_model: str = "minilm"
    device: Optional[str] = None
    batch_size: int = 32
    skip_patterns: list[str] = field(default_factory=lambda: [
        "__pycache__", ".git", "node_modules", "venv", ".venv", "build", "dist", ".tox", ".pytest_cache", "*.pyc", ".mypy_cache", ".ruff_cache"
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
            
            for file_path in files:
                try:
                    units_added = self._index_file(file_path, repo_path)
                    total_units += units_added
                except Exception as e:
                    self.console.print(f"[yellow]Warning: Failed to index {file_path}: {e}[/yellow]")
                progress.update(task, advance=1)

        stats = self.vector_store.get_stats(self.repo_id)
        self.console.print(f"[bold green]Indexed {total_units} code units![/bold green]")
        
        return {
            "repo_id": self.repo_id,
            "repo_path": str(repo_path),
            "files_indexed": len(files),
            "units_indexed": total_units,
            "stats": stats,
        }

    def _get_or_create_repo(self, repo_path: Path) -> str:
        repo_id = hashlib.sha256(str(repo_path).encode()).hexdigest()[:16]
        
        detected_lang = self._detect_language(repo_path)

        repo = Repository(
            id=repo_id,
            name=repo_path.name,
            path=str(repo_path),
            language=detected_lang,
            indexed_at=datetime.utcnow(),
        )
        self.vector_store.add_repository(repo)
        self.console.print(f"Prepared repository: {repo_id} (language: {detected_lang})")

        return repo_id

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

    def _discover_files(self, repo_path: Path) -> list[Path]:
        files = []
        for file_path in repo_path.rglob("*"):
            if file_path.is_file() and not self._should_skip(file_path):
                if file_path.suffix in MultiLanguageParser.supported_extensions():
                    files.append(file_path)
        return files

    def _should_skip(self, path: Path) -> bool:
        path_str = str(path)
        for pattern in self.config.skip_patterns:
            if pattern.startswith("*"):
                if path_str.endswith(pattern[1:]):
                    return True
            elif pattern in path_str:
                return True
        return False

    def _index_file(self, file_path: Path, repo_root: Path) -> int:
        relative_path = str(file_path.relative_to(repo_root))
        
        parser = get_parser_for_file(str(file_path))
        if not parser:
            return 0
        
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        
        file_hash = self.vector_store.compute_file_hash(relative_path, content)
        existing_hash = self.vector_store.get_file_hash(self.repo_id, relative_path)
        if existing_hash == file_hash:
            return 0
        if existing_hash is not None:
            self.vector_store.delete_by_file(self.repo_id, relative_path)
        
        try:
            parsed = parser.parse_file(content, relative_path, self.repo_id)
        except Exception as e:
            self.console.print(f"[dim]Parse error: {file_path}: {e}[/dim]")
            return 0
        
        all_units = self._flatten_units(parsed)
        all_units.append(parsed)
        
        code_texts = []
        code_unit_map = {}
        for u in all_units:
            if u.code:
                code_texts.append(u.code[:2000])
                code_unit_map[u.id] = u
        
        if not code_texts:
            return 0
        
        self._ensure_embedder_loaded()
        
        try:
            embeddings_list = self.embedder.embed_batch(code_texts)
        except Exception as e:
            self.console.print(f"[dim]Embedding error: {file_path}: {e}[/dim]")
            return 0
        
        embeddings_map = {}
        for i, (unit_id, unit) in enumerate(code_unit_map.items()):
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
