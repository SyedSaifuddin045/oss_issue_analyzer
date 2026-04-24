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
    repo_path: Annotated[str, typer.Argument(help="Path to the repository")],
    issue_url: Optional[str] = None,
):
    pass


@app.command()
def index(
    repo_path: Annotated[str, typer.Argument(help="Path to the repository")],
    db_path: Annotated[str, typer.Option("--db-path", help="Path to the index database")] = ".data/index.lance",
    embedder: Annotated[str, typer.Option("--embedder", help="Embedding model (nomic, minilm)")] = "minilm",
    force: Annotated[bool, typer.Option("--force", help="Force re-index from scratch")] = False,
):
    from src.indexer.indexer import CodeIndexer, IndexerConfig
    import hashlib
    
    if force:
        console.print("[yellow]Force re-index enabled, clearing existing data...[/yellow]")
        from src.indexer.storage import get_index as get_storage_index
        idx = get_storage_index(db_path)
        repo_id = hashlib.sha256(str(repo_path).encode()).hexdigest()[:16]
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
