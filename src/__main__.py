from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

__version__ = "1.0.0"

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
def setup(
    provider: Annotated[
        Optional[str],
        typer.Option(
            "--provider",
            "-p",
            help="Provider name (openai, anthropic, google, azure_openai)",
        ),
    ] = None,
    api_key: Annotated[
        Optional[str],
        typer.Option(
            "--api-key",
            help="API key for the provider",
        ),
    ] = None,
    test: Annotated[
        bool,
        typer.Option(
            "--test",
            "-t",
            help="Test the connection after configuration",
        ),
    ] = False,
    list_providers: Annotated[
        bool,
        typer.Option(
            "--list",
            "-l",
            help="List available providers based on .env configuration",
        ),
    ] = False,
    clear: Annotated[
        bool,
        typer.Option(
            "--clear",
            help="Clear saved provider configuration",
        ),
    ] = False,
):
    from src.analyzer.config import (
        ProviderName,
        clear_provider_config,
        get_available_providers,
        get_credentials,
        save_provider_config,
        test_provider_connection,
    )
    from src.analyzer.llm_provider import get_provider_instance
    
    if clear:
        clear_provider_config()
        console.print("[green]Provider configuration cleared.[/green]")
        return
    
    if list_providers:
        available = get_available_providers()
        creds = get_credentials()
        
        table = Table(title="Available AI Providers")
        table.add_column("Provider", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Env Variable", style="yellow")
        
        status_for = {
            ProviderName.OPENAI: ("OpenAI", creds.openai_api_key),
            ProviderName.ANTHROPIC: ("Anthropic", creds.anthropic_api_key),
            ProviderName.GOOGLE: ("Google", creds.google_api_key),
            ProviderName.AZURE_OPENAI: ("Azure OpenAI", creds.azure_openai_api_key),
        }
        
        for prov in [
            ProviderName.OPENAI,
            ProviderName.ANTHROPIC,
            ProviderName.GOOGLE,
            ProviderName.AZURE_OPENAI,
        ]:
            name, key = status_for[prov]
            status = "✓ Configured" if key else "✗ Not configured"
            env_var = {
                ProviderName.OPENAI: "OPENAI_API_KEY",
                ProviderName.ANTHROPIC: "ANTHROPIC_API_KEY",
                ProviderName.GOOGLE: "GOOGLE_API_KEY",
                ProviderName.AZURE_OPENAI: "AZURE_OPENAI_API_KEY",
            }[prov]
            table.add_row(name, status, env_var)
        
        console.print(table)
        
        if available:
            console.print(f"\n[green]Detected provider(s) in environment:[/green] {', '.join(p.value for p in available)}")
        
        return
    
    if provider is None:
        available = get_available_providers()
        
        if not available:
            console.print("[yellow]No API keys detected in environment.[/yellow]")
            console.print("Please configure one of the following:")
            console.print("  - OPENAI_API_KEY")
            console.print("  - ANTHROPIC_API_KEY")
            console.print("  - GOOGLE_API_KEY")
            console.print("  - AZURE_OPENAI_API_KEY + AZURE_OPENAI_ENDPOINT")
            console.print("\nOr run with --provider to specify one anyway.")
            
            provider = Prompt.ask(
                "Select provider",
                choices=["openai", "anthropic", "google", "azure_openai"],
                default="openai",
            )
        elif len(available) == 1:
            provider = available[0].value
            console.print(f"[cyan]Detected {provider} in environment.[/cyan]")
        else:
            console.print(f"[cyan]Multiple providers detected: {', '.join(p.value for p in available)}[/cyan]")
            provider = Prompt.ask(
                "Select provider",
                choices=["openai", "anthropic", "google", "azure_openai"],
                default=available[0].value,
            )
    
    provider_lower = provider.lower()
    
    valid_providers = {
        "openai": ProviderName.OPENAI,
        "anthropic": ProviderName.ANTHROPIC,
        "google": ProviderName.GOOGLE,
        "azure_openai": ProviderName.AZURE_OPENAI,
    }
    
    if provider_lower not in valid_providers:
        console.print(f"[red]Invalid provider: {provider}[/red]")
        console.print("Valid providers: openai, anthropic, google, azure_openai")
        raise typer.Exit(1)
    
    provider_enum = valid_providers[provider_lower]
    
    env_key_for_provider = {
        ProviderName.OPENAI: "OPENAI_API_KEY",
        ProviderName.ANTHROPIC: "ANTHROPIC_API_KEY",
        ProviderName.GOOGLE: "GOOGLE_API_KEY",
        ProviderName.AZURE_OPENAI: "AZURE_OPENAI_API_KEY",
    }
    
    creds = get_credentials()
    key_is_in_env = {
        ProviderName.OPENAI: bool(creds.openai_api_key),
        ProviderName.ANTHROPIC: bool(creds.anthropic_api_key),
        ProviderName.GOOGLE: bool(creds.google_api_key),
        ProviderName.AZURE_OPENAI: bool(creds.azure_openai_api_key),
    }
    
    if api_key is None and not key_is_in_env[provider_enum]:
        api_key = Prompt.ask(
            f"Enter API key for {provider}",
            password=True,
        )
    
    if api_key and not key_is_in_env[provider_enum]:
        console.print(f"[dim]Note: Key will be saved to config (not to .env)[/dim]")
        save_provider_config(provider_enum)
    elif key_is_in_env[provider_enum]:
        save_provider_config(provider_enum)
        console.print(f"[green]Using {provider} from environment.[/green]")
    
    if test:
        console.print(f"[cyan]Testing {provider} connection...[/cyan]")
        success, message = test_provider_connection(provider_enum)
        
        if success:
            console.print(f"[green]✓ {message}[/green]")
        else:
            console.print(f"[red]✗ {message}[/red]")
            raise typer.Exit(1)
    
    console.print(f"[green]Provider '{provider}' configured successfully![/green]")


@app.command()
def analyze(
    issue_ref: Annotated[str, typer.Argument(help="Issue URL, issue number, or path to local markdown file")],
    repo_path: Annotated[Optional[str], typer.Option("--repo", "-r", help="Path to indexed repository (default: current dir)")] = None,
    db_path: Annotated[Optional[str], typer.Option("--db-path", help="Path to index database (auto-detect if omitted)")] = None,
    embedder: Annotated[str, typer.Option("--embedder", help="Embedding model (nomic, minilm)")] = "minilm",
    limit: Annotated[int, typer.Option("--limit", "-l", help="Number of code units to retrieve")] = 10,
    gh_repo: Annotated[Optional[str], typer.Option("--gh-repo", help="GitHub repo (owner/repo) - auto-detected if not provided)")] = None,
    ai_provider: Annotated[Optional[str], typer.Option("--ai-provider", help="AI provider to use (openai, anthropic, google, azure_openai)")] = None,
    no_ai: Annotated[bool, typer.Option("--no-ai", help="Disable AI scoring, use heuristics only")] = False,
):
    from pathlib import Path
    import hashlib
    import subprocess
    
    from src.github.client import GitHubClient, load_issue_from_file
    from src.analyzer.preprocessor import IssuePreprocessor
    from src.analyzer.retriever import HybridRetriever
    from src.analyzer.scorer import HeuristicScorer
    from src.indexer.storage import VectorStore
    from src.analyzer.config import get_ai_config, ProviderName
    from src.analyzer.llm_provider import get_provider_instance
    from src.analyzer.ai_scorer import AIScorer
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
        is_compatible, compatibility_error = vector_store.validate_repo_compatibility(repo_id)
        if not is_compatible:
            console.print(f"[bold red]Error:[/bold red] {compatibility_error}")
            raise typer.Exit(1)
        existing_repo = vector_store.get_repository(repo_id)
        if not existing_repo:
            console.print("[bold red]Error:[/bold red] Repository not indexed. Run 'oss-issue-analyzer index <repo_path>' first.")
            raise typer.Exit(1)
        
        if Path(issue_ref).exists():
            issue = load_issue_from_file(issue_ref)
            issue_comments = []
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
                    issue_comments = client.get_issue_comments(parsed_owner, parsed_repo, parsed_num)
                else:
                    issue = client.get_issue(owner, repo, issue_num)
                    issue_comments = client.get_issue_comments(owner, repo, issue_num)
            except ValueError as exc:
                console.print(f"[bold red]Error:[/bold red] {exc}")
                raise typer.Exit(1)
            finally:
                client.close()
        
        preprocessor = IssuePreprocessor()
        processed = preprocessor.process(issue.title, issue.body)
        processed.comments = [c.body for c in issue_comments]
        
        retriever = HybridRetriever(db_path=db_path)
        retrieval = retriever.search(processed, repo_id, limit=limit)
        
        ai_config = get_ai_config()
        
        heuristic_scorer = HeuristicScorer(db_path=db_path)
        
        use_ai = not no_ai and ai_config.is_configured
        
        if ai_provider:
            provider_name_map = {
                "openai": ProviderName.OPENAI,
                "anthropic": ProviderName.ANTHROPIC,
                "google": ProviderName.GOOGLE,
                "azure_openai": ProviderName.AZURE_OPENAI,
            }
            provider_enum = provider_name_map.get(ai_provider.lower())
            if provider_enum:
                provider = get_provider_instance(provider_enum)
                if provider:
                    ai_scorer = AIScorer(provider=provider, fallback_scorer=heuristic_scorer)
                    result = ai_scorer.score(retrieval)
                    use_ai = True
                else:
                    console.print(f"[yellow]Warning: Could not initialize {ai_provider}, falling back to heuristics[/yellow]")
                    result = heuristic_scorer.score(retrieval)
            else:
                console.print(f"[yellow]Warning: Unknown provider '{ai_provider}', using heuristics[/yellow]")
                result = heuristic_scorer.score(retrieval)
        elif use_ai:
            provider = get_provider_instance(ai_config.provider)
            if provider:
                ai_scorer = AIScorer(provider=provider, fallback_scorer=heuristic_scorer)
                result = ai_scorer.score(retrieval)
            else:
                console.print("[yellow]Warning: AI provider not available, using heuristics[/yellow]")
                result = heuristic_scorer.score(retrieval)
        else:
            result = heuristic_scorer.score(retrieval)
        
        scoring_method = "AI" if use_ai else "Heuristic"
        
        if global_options.json:
            import json
            output = {
                "issue_title": result.issue_title,
                "difficulty": result.overall_difficulty.difficulty,
                "confidence": result.overall_difficulty.confidence,
                "raw_score": result.overall_difficulty.raw_score,
                "relative_percentile": result.overall_difficulty.relative_percentile,
                "scoring_method": scoring_method,
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
        
        method_badge = f" [{scoring_method}]" if use_ai else ""
        
        console.print(Panel(
            f"[bold]Difficulty:[/bold] [{difficulty_color}]{result.overall_difficulty.difficulty.upper()}[/] (conf: {result.overall_difficulty.confidence:.0%}){method_badge}" + 
            (f"\n[bold]Relative:[/bold] Easier than {result.overall_difficulty.relative_percentile:.0%}" 
             if result.overall_difficulty.relative_percentile else ""),
            title=f"Issue: {issue.title[:60]}{'...' if len(issue.title) > 60 else ''}",
            border_style=difficulty_color,
        ))
        
        console.print("\n[bold]Relevant files:[/bold]")
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
        
        if not use_ai and ai_config.enabled and ai_config.provider != ProviderName.NONE and not no_ai:
            console.print("\n[dim]Note: AI scoring requested but not available. Used heuristic scoring.[/dim]")
        elif not use_ai and not no_ai:
            console.print("\n[dim]Tip: Run 'oss-issue-analyzer setup' to enable AI-powered scoring[/dim]")
        
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
    index_mode: Annotated[str, typer.Option("--index-mode", help="Index mode (mixed, code-only)")] = "mixed",
    force: Annotated[bool, typer.Option("--force", help="Force re-index from scratch")] = False,
):
    from src.indexer.indexer import CodeIndexer, IndexerConfig
    import hashlib
    import shutil
    from pathlib import Path
    from src.indexer.storage import VectorStore
    
    repo_dir = Path(repo_path).resolve()
    if db_path is None:
        db_path = str(repo_dir / ".oss-index" / "index.lance")

    if index_mode not in {"mixed", "code-only"}:
        console.print("[bold red]Error:[/bold red] --index-mode must be 'mixed' or 'code-only'.")
        raise typer.Exit(1)
    
    if force:
        console.print("[yellow]Force re-index enabled, clearing existing data...[/yellow]")
        db_dir = Path(db_path)
        if db_dir.exists():
            shutil.rmtree(db_dir)
    else:
        repo_id = hashlib.sha256(str(repo_dir).encode()).hexdigest()[:16]
        vector_store = VectorStore(db_path)
        is_compatible, compatibility_error = vector_store.validate_repo_compatibility(repo_id)
        if not is_compatible:
            console.print(f"[bold red]Error:[/bold red] {compatibility_error}")
            raise typer.Exit(1)
    
    config = IndexerConfig(
        repo_path=repo_path,
        db_path=db_path,
        embedder_model=embedder,
        index_mode=index_mode,
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
            console.print(f"  Index mode: {result['index_mode']}")
            console.print(f"  Files indexed: {result['files_indexed']}")
            console.print(f"  Indexed units: {result['units_indexed']}")
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