from typing import Annotated, Optional

import typer
from rich.console import Console

__version__ = "0.1.0"

app = typer.Typer(add_completion=False, invoke_without_command=True)
console = Console()


class GlobalOptions:
    def __init__(
        self,
        verbose: bool = False,
        json: bool = False,
        api_key: Optional[str] = None,
    ):
        self.verbose = verbose
        self.json = json
        self.api_key = api_key


global_options: GlobalOptions = GlobalOptions()


@app.callback()
def main(
    ctx: typer.Context,
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable verbose output"
    ),
    json: bool = typer.Option(False, "--json", help="Output in JSON format"),
    api_key: Annotated[
        Optional[str], typer.Option("--api-key", help="API key for authentication")
    ] = None,
    version: bool = typer.Option(
        False, "--version", help="Show version and exit", is_flag=True, flag_value=True
    ),
):
    global_options.verbose = verbose
    global_options.json = json
    global_options.api_key = api_key

    if version:
        console.print(f"oss-issue-analyzer version {__version__}")
        raise typer.Exit()

    if ctx.invoked_subcommand is None:
        console.print("[bold green]Welcome to OSS Issue Analyzer![/bold green]")
        console.print("Application started successfully.")


@app.command()
def start(ctx: typer.Context):
    console.print("[bold green]Welcome to OSS Issue Analyzer![/bold green]")
    console.print("Application started successfully.")


@app.command()
def analyze(
    issue_ref: Annotated[str, typer.Argument(help="Issue URL, issue number, or path to local markdown file")],
    repo_path: Annotated[Optional[str], typer.Option("--repo", "-r", help="Path to indexed repository (default: current dir)")] = None,
    db_path: Annotated[Optional[str], typer.Option("--db-path", help="Path to index database (auto-detect if omitted)")] = None,
    embedder: Annotated[str, typer.Option("--embedder", help="Embedding model (nomic, minilm)")] = "minilm",
    limit: Annotated[int, typer.Option("--limit", "-l", help="Number of code units to retrieve")] = 10,
    gh_repo: Annotated[Optional[str], typer.Option("--gh-repo", help="GitHub repo (owner/repo) - auto-detected if not provided)")] = None,
):
    from pathlib import Path
    import hashlib
    import subprocess
    
    from src.github.client import GitHubClient, load_issue_from_file
    from src.analyzer.preprocessor import IssuePreprocessor
    from src.analyzer.retriever import HybridRetriever
    from src.analyzer.scorer import HeuristicScorer
    from src.indexer.storage import VectorStore
    from rich.panel import Panel
    
    def get_github_remote(repo_dir: Path) -> tuple[str, str]:
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            url = result.stdout.strip()
            if "github.com" in url:
                if url.startswith("git@github.com:"):
                    parts = url.replace("git@github.com:", "").replace(".git", "").split("/")
                else:
                    parts = url.replace("https://github.com/", "").replace(".git", "").split("/")
                if len(parts) >= 2:
                    return parts[0], parts[1]
        except Exception:
            pass
        return None, None
    
    try:
        if repo_path:
            repo_dir = Path(repo_path).resolve()
        else:
            repo_dir = Path(".").resolve()
        
        if not repo_dir.exists():
            console.print(f"[bold red]Error:[/bold red] Repository path does not exist: {repo_dir}")
            raise typer.Exit(1)
        if not repo_dir.is_dir():
            console.print(f"[bold red]Error:[/bold red] Repository path must be a directory: {repo_dir}")
            raise typer.Exit(1)
        
        if db_path is None:
            db_path = str(repo_dir / ".oss-index" / "index.lance")
        
        repo_id = hashlib.sha256(str(repo_dir).encode()).hexdigest()[:16]
        
        vector_store = VectorStore(db_path)
        existing_repo = vector_store.get_repository(repo_id)
        if not existing_repo:
            console.print("[bold red]Error:[/bold red] Repository not indexed. Run 'oss-issue-analyzer index <repo_path>' first.")
            raise typer.Exit(1)
        
        if Path(issue_ref).exists():
            issue = load_issue_from_file(issue_ref)
        else:
            owner, repo = gh_repo, None
            if not owner:
                owner, repo = get_github_remote(repo_dir)
            
            client = GitHubClient(token=global_options.api_key)
            try:
                if not owner or not repo:
                    console.print("[bold red]Error:[/bold red] Cannot determine GitHub repo. Use --gh-repo flag or run in a git repo with remote origin.")
                    raise typer.Exit(1)
                
                issue_num = int(issue_ref) if issue_ref.isdigit() else None
                if not issue_num:
                    parsed_owner, parsed_repo, parsed_num = client.parse_issue_ref(issue_ref)
                    issue = client.get_issue(parsed_owner, parsed_repo, parsed_num)
                else:
                    issue = client.get_issue(owner, repo, issue_num)
            except ValueError as exc:
                console.print(f"[bold red]Error:[/bold red] {exc}")
                raise typer.Exit(1)
            finally:
                client.close()
        
        preprocessor = IssuePreprocessor()
        processed = preprocessor.process(issue.title, issue.body)
        
        retriever = HybridRetriever(db_path=db_path)
        retrieval = retriever.search(processed, repo_id, limit=limit)
        
        scorer = HeuristicScorer(db_path=db_path)
        result = scorer.score(retrieval)
        
        if global_options.json:
            import json
            output = {
                "issue_title": result.issue_title,
                "difficulty": result.overall_difficulty.difficulty,
                "confidence": result.overall_difficulty.confidence,
                "raw_score": result.overall_difficulty.raw_score,
                "relative_percentile": result.overall_difficulty.relative_percentile,
                "units": [
                    {
                        "path": us.unit.path,
                        "name": us.unit.name,
                        "type": us.unit.unit_type,
                        "score": us.difficulty_score,
                    }
                    for us in result.units
                ],
                "positive_signals": result.positive_signals,
                "warning_signals": result.warning_signals,
                "suggested_approach": result.suggested_approach,
                "is_good_first_issue": result.is_good_first_issue,
            }
            console.print(json.dumps(output, indent=2))
            return
        
        difficulty_color = {
            "easy": "green",
            "medium": "yellow",
            "hard": "red",
        }.get(result.overall_difficulty.difficulty, "white")
        
        console.print(Panel(
            f"[bold]Difficulty:[/bold] [{difficulty_color}]{result.overall_difficulty.difficulty.upper()}[/] (conf: {result.overall_difficulty.confidence:.0%})" + 
            (f"\n[bold]Relative:[/bold] Easier than {result.overall_difficulty.relative_percentile:.0%}" 
             if result.overall_difficulty.relative_percentile else ""),
            title=f"Issue: {issue.title[:60]}{'...' if len(issue.title) > 60 else ''}",
            border_style=difficulty_color,
        ))
        
        console.print("\n[bold]Files involved:[/bold]")
        for us in result.units[:5]:
            console.print(f"  → {us.unit.path}")
        
        if result.suggested_approach:
            console.print("\n[bold]Suggested approach:[/bold]")
            for suggestion in result.suggested_approach:
                console.print(f"  {suggestion}")
        
        if result.positive_signals:
            console.print("\n[green][bold]Contributor signals:[/bold][/green]")
            for signal in result.positive_signals:
                console.print(f"  ✓ {signal}")
        
        if result.warning_signals:
            console.print("\n[yellow][bold]Warning signals:[/bold][/yellow]")
            for signal in result.warning_signals:
                console.print(f"  ⚠ {signal}")
        
        if result.is_good_first_issue:
            console.print("\n[bold green]🎯 This issue is suitable as a good first issue![/bold green]")
        
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        if global_options.verbose:
            import traceback
            console.print(traceback.format_exc())
        raise typer.Exit(1)


@app.command()
def index(
    repo_path: Annotated[str, typer.Argument(help="Path to the repository")],
    db_path: Annotated[Optional[str], typer.Option("--db-path", help="Path to index database (default: <repo_path>/.oss-index)")] = None,
    embedder: Annotated[str, typer.Option("--embedder", help="Embedding model (nomic, minilm)")] = "minilm",
    force: Annotated[bool, typer.Option("--force", help="Force re-index from scratch")] = False,
):
    from src.indexer.indexer import CodeIndexer, IndexerConfig
    import hashlib
    from pathlib import Path
    
    repo_dir = Path(repo_path).resolve()
    if db_path is None:
        db_path = str(repo_dir / ".oss-index" / "index.lance")
    
    if force:
        console.print("[yellow]Force re-index enabled, clearing existing data...[/yellow]")
        from src.indexer.storage import get_index as get_storage_index
        idx = get_storage_index(db_path)
        repo_id = hashlib.sha256(str(repo_dir).encode()).hexdigest()[:16]
        idx.delete_by_repo(repo_id)
    
    config = IndexerConfig(
        repo_path=repo_path,
        db_path=db_path,
        embedder_model=embedder,
    )
    indexer = CodeIndexer(config)
    
    try:
        result = indexer.run()
        
        if global_options.json:
            import json
            console.print(json.dumps(result, indent=2))
        else:
            console.print("\n[bold green]Indexing complete![/bold green]")
            console.print(f"  Repository: {result['repo_id']}")
            console.print(f"  Files indexed: {result['files_indexed']}")
            console.print(f"  Code units: {result['units_indexed']}")
            stats = result['stats']
            console.print(f"  - Files: {stats['files']}")
            console.print(f"  - Classes: {stats['classes']}")
            console.print(f"  - Functions: {stats['functions']}")
            console.print(f"  - Methods: {stats['methods']}")
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)


@app.command()
def config(
    action: Annotated[str, typer.Argument(help="Action to perform (set, get, list)")],
    key: Optional[str] = None,
    value: Optional[str] = None,
):
    pass


if __name__ == "__main__":
    app()
