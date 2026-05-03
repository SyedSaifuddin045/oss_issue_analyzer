from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.panel import Panel

__version__ = "1.0.2"

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


def _build_issue_comment_contexts(comments) -> list:
    from src.analyzer.preprocessor import IssueCommentContext

    return [
        IssueCommentContext(
            body=comment.body,
            author=comment.user_login,
            is_maintainer=getattr(comment, "is_maintainer", False),
            reactions=getattr(comment, "reactions", 0),
        )
        for comment in comments
    ]


def _serialize_result(result) -> dict:
    return {
        "issue_title": result.issue_title,
        "overall_difficulty": {
            "raw_score": result.overall_difficulty.raw_score,
            "difficulty": result.overall_difficulty.difficulty,
            "confidence": result.overall_difficulty.confidence,
            "relative_percentile": result.overall_difficulty.relative_percentile,
        },
        "units": [
            {
                "unit": {
                    "id": unit_score.unit.id,
                    "path": unit_score.unit.path,
                    "name": unit_score.unit.name,
                    "unit_type": unit_score.unit.unit_type,
                    "language": unit_score.unit.language,
                    "start_line": unit_score.unit.start_line,
                    "end_line": unit_score.unit.end_line,
                    "signature": unit_score.unit.signature,
                    "docstring": unit_score.unit.docstring,
                    "code": unit_score.unit.code,
                    "asset_kind": unit_score.unit.asset_kind,
                    "score": unit_score.unit.score,
                    "match_type": unit_score.unit.match_type,
                    "is_test": unit_score.unit.is_test,
                    "match_reasons": unit_score.unit.match_reasons,
                },
                "difficulty_score": unit_score.difficulty_score,
                "signals": [
                    {"is_positive": signal.is_positive, "message": signal.message}
                    for signal in unit_score.signals
                ],
            }
            for unit_score in result.units
        ],
        "positive_signals": result.positive_signals,
        "warning_signals": result.warning_signals,
        "suggested_approach": result.suggested_approach,
        "is_good_first_issue": result.is_good_first_issue,
        "core_problem": result.core_problem,
        "strategic_guidance": result.strategic_guidance,
        "why_these_files": result.why_these_files,
        "uncertainty_notes": result.uncertainty_notes,
    }


def _deserialize_result(result_dict: dict):
    from src.analyzer.retriever import RetrievedUnit
    from src.analyzer.scorer import ContributorSignal, DifficultyScore, ScoringResult, UnitScore

    overall_difficulty = DifficultyScore(**result_dict["overall_difficulty"])
    units = []
    for unit_entry in result_dict.get("units", []):
        unit = RetrievedUnit(**unit_entry["unit"])
        unit_score = UnitScore(
            unit=unit,
            difficulty_score=unit_entry["difficulty_score"],
            signals=[
                ContributorSignal(**signal)
                for signal in unit_entry.get("signals", [])
            ],
        )
        units.append(unit_score)

    return ScoringResult(
        issue_title=result_dict["issue_title"],
        overall_difficulty=overall_difficulty,
        units=units,
        positive_signals=result_dict.get("positive_signals", []),
        warning_signals=result_dict.get("warning_signals", []),
        suggested_approach=result_dict.get("suggested_approach", []),
        is_good_first_issue=result_dict.get("is_good_first_issue", False),
        core_problem=result_dict.get("core_problem", ""),
        strategic_guidance=result_dict.get("strategic_guidance", []),
        why_these_files=result_dict.get("why_these_files", []),
        uncertainty_notes=result_dict.get("uncertainty_notes", []),
    )


def _print_analysis_details(result) -> None:
    console.print("\n[bold]Relevant files:[/bold]")
    for unit_score in result.units[:5]:
        console.print(f"  → {unit_score.unit.path}")

    if result.why_these_files:
        console.print("\n[bold]Why these files:[/bold]")
        for explanation in result.why_these_files:
            console.print(f"  → {explanation}")

    if result.core_problem:
        console.print(f"\n[bold cyan]Core problem:[/bold cyan] {result.core_problem}")

    if result.strategic_guidance:
        console.print("\n[bold]Senior guidance:[/bold]")
        for guidance in result.strategic_guidance:
            console.print(f"  → {guidance}")

    if result.suggested_approach:
        console.print("\n[bold]Action steps:[/bold]")
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

    if result.uncertainty_notes:
        console.print("\n[bold]Uncertainty notes:[/bold]")
        for note in result.uncertainty_notes:
            console.print(f"  → {note}")


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
        save_provider_config(provider_enum, api_key=api_key)
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
    no_cache: Annotated[bool, typer.Option("--no-cache", help="Force re-fetch from GitHub")] = False,
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
                    owner, repo = parsed_owner, parsed_repo
                    issue = client.get_issue(parsed_owner, parsed_repo, parsed_num)
                    issue_comments = client.get_issue_comments(
                        parsed_owner,
                        parsed_repo,
                        parsed_num,
                        issue_author=issue.user_login,
                    )
                else:
                    issue = client.get_issue(owner, repo, issue_num)
                    issue_comments = client.get_issue_comments(
                        owner,
                        repo,
                        issue_num,
                        issue_author=issue.user_login,
                    )
            except ValueError as exc:
                console.print(f"[bold red]Error:[/bold red] {exc}")
                raise typer.Exit(1)
            finally:
                client.close()
        
        preprocessor = IssuePreprocessor()
        processed = preprocessor.process(issue.title, issue.body)
        processed.comments = _build_issue_comment_contexts(issue_comments)
        
        retriever = HybridRetriever(db_path=db_path)
        retrieval = retriever.search(processed, repo_id, limit=limit)
        
        ai_config = get_ai_config()
        heuristic_scorer = HeuristicScorer(db_path=db_path)
        
        use_ai = not no_ai and ai_config.is_configured
        result = None
        cache_used = False
        
        from src.analyzer.cache import (
            get_cache_dir, load_analysis_cache, save_analysis_cache,
            update_cached_issue_difficulty,
        )
        cache_dir = get_cache_dir(repo_dir)
        
        issue_num = None
        if not Path(issue_ref).exists() and issue_ref.isdigit():
            issue_num = int(issue_ref)
        elif "github.com" in issue_ref:
            try:
                client_temp = GitHubClient(token=global_options.api_key)
                try:
                    parsed = client_temp.parse_issue_ref(issue_ref)
                    issue_num = parsed[2]
                finally:
                    client_temp.close()
            except Exception:
                pass
        
        analysis_signature = None
        configured_ai_scorer = None

        if ai_provider:
            provider_name_map = {
                "openai": ProviderName.OPENAI,
                "anthropic": ProviderName.ANTHROPIC,
                "google": ProviderName.GOOGLE,
                "azure_openai": ProviderName.AZURE_OPENAI,
            }
            provider_enum = provider_name_map.get(ai_provider.lower())
            provider = get_provider_instance(provider_enum) if provider_enum else None
            if provider:
                configured_ai_scorer = AIScorer(
                    provider=provider,
                    fallback_scorer=heuristic_scorer,
                    temperature=ai_config.temperature,
                    max_tokens=ai_config.max_tokens,
                    context_unit_budget=min(limit, ai_config.context_unit_budget),
                )
                analysis_signature = configured_ai_scorer.get_analysis_signature()
                use_ai = True
            elif provider_enum:
                console.print(f"[yellow]Warning: Could not initialize {ai_provider}, falling back to heuristics[/yellow]")
                use_ai = False
            else:
                console.print(f"[yellow]Warning: Unknown provider '{ai_provider}', using heuristics[/yellow]")
                use_ai = False
        elif use_ai:
            provider = get_provider_instance(ai_config.provider)
            if provider:
                configured_ai_scorer = AIScorer(
                    provider=provider,
                    fallback_scorer=heuristic_scorer,
                    temperature=ai_config.temperature,
                    max_tokens=ai_config.max_tokens,
                    context_unit_budget=min(limit, ai_config.context_unit_budget),
                )
                analysis_signature = configured_ai_scorer.get_analysis_signature()
            else:
                console.print("[yellow]Warning: AI provider not available, using heuristics[/yellow]")
                use_ai = False

        if issue_num and not no_cache:
            cached_analysis = load_analysis_cache(
                repo_dir,
                owner,
                repo,
                issue_num,
                expected_signature=analysis_signature,
            )
            if cached_analysis:
                try:
                    result = _deserialize_result(cached_analysis["result"])
                    cache_used = True
                    if global_options.verbose:
                        console.print("[dim][Analysis cached][/dim]")
                except (KeyError, TypeError, ValueError):
                    if global_options.verbose:
                        console.print(f"[yellow]Warning: Cache format mismatch, re-analyzing[/yellow]")
                    result = None
                    cache_used = False

        if result is None:
            if configured_ai_scorer and use_ai:
                result = configured_ai_scorer.score(retrieval)
            else:
                result = heuristic_scorer.score(retrieval)
            
            if issue_num:
                save_analysis_cache(
                    repo_dir, owner, repo, issue_num,
                    _serialize_result(result),
                    quick_score_original=result.overall_difficulty.raw_score,
                    analysis_signature=analysis_signature or "heuristic-v1",
                    scoring_method="ai" if configured_ai_scorer and use_ai else "heuristic",
                )
        
        scoring_method = "AI" if use_ai else "Heuristic"
        if cache_used:
            scoring_method += " [cached]"
        
        if global_options.json:
            import json
            output = {
                "issue_title": result.issue_title,
                "difficulty": result.overall_difficulty.difficulty,
                "confidence": result.overall_difficulty.confidence,
                "raw_score": result.overall_difficulty.raw_score,
                "relative_percentile": result.overall_difficulty.relative_percentile,
                "scoring_method": scoring_method,
                "core_problem": result.core_problem,
                "strategic_guidance": result.strategic_guidance,
                "why_these_files": result.why_these_files,
                "uncertainty_notes": result.uncertainty_notes,
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
        
        method_badge = f" [{scoring_method}]" if use_ai or cache_used else ""
        
        console.print(Panel(
            f"[bold]Difficulty:[/bold] [{difficulty_color}]{result.overall_difficulty.difficulty.upper()}[/] (conf: {result.overall_difficulty.confidence:.0%}){method_badge}" + 
            (f"\n[bold]Relative:[/bold] Easier than {result.overall_difficulty.relative_percentile:.0%}" 
             if result.overall_difficulty.relative_percentile else ""),
            title=f"Issue: {issue.title[:60]}{'...' if len(issue.title) > 60 else ''}",
            border_style=difficulty_color,
        ))
        _print_analysis_details(result)
        
        if result.is_good_first_issue:
            console.print("\n[bold green]🎯 This issue is suitable as a good first issue![/bold green]")
        
        if not use_ai and ai_config.enabled and ai_config.provider != ProviderName.NONE and not no_ai:
            console.print("\n[dim]Note: AI scoring requested but not available. Used heuristic scoring.[/dim]")
        elif not use_ai and not no_ai and not cache_used:
            console.print("\n[dim]Tip: Run 'oss-issue-analyzer setup' to enable AI-powered scoring[/dim]")
        
        if use_ai and issue_num:
            quick_score_data = None
            from src.analyzer.cache import load_issue_cache
            cached_quick = load_issue_cache(repo_dir, owner, repo, "open")
            if cached_quick:
                quick_score_data = next(
                    (i for i in cached_quick.get("issues", []) if i.get("number") == issue_num),
                    None
                )
            
            if quick_score_data and quick_score_data.get("difficulty") != result.overall_difficulty.difficulty:
                console.print(f"\n[yellow]Discrepancy detected![/yellow]")
                console.print(f"  Quick score: {quick_score_data['difficulty']} (conf: {quick_score_data['confidence']:.0%})")
                console.print(f"  AI score:    {result.overall_difficulty.difficulty} (conf: {result.overall_difficulty.confidence:.0%})")
                
                if Confirm.ask("Update cached quick score to match AI?"):
                    update_cached_issue_difficulty(
                        repo_dir, owner, repo, issue_num,
                        result.overall_difficulty.difficulty,
                        result.overall_difficulty.raw_score,
                    )
                    console.print("[green]Cached quick score updated![/green]")
        
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        if global_options.verbose:
            import traceback
            console.print(traceback.format_exc())
        raise typer.Exit(1)


@app.command(name="list-issues")
def list_issues(
    repo_path: Annotated[Optional[str], typer.Option("--repo", "-r", help="Path to repository (default: current dir)")] = None,
    state: Annotated[str, typer.Option("--state", help="Issue state: open, closed, all")] = "open",
    sort_by: Annotated[str, typer.Option("--sort", help="Sort by: difficulty, number, created")] = "difficulty",
    filter_difficulty: Annotated[Optional[str], typer.Option("--filter-difficulty", help="Filter by difficulty: easy, medium, hard")] = None,
    filter_label: Annotated[Optional[str], typer.Option("--filter-label", help="Filter by label (partial match)")] = None,
    limit: Annotated[int, typer.Option("--limit", help="Max issues to show (0=all)")] = 0,
    cache_ttl: Annotated[int, typer.Option("--cache-ttl", help="Cache TTL in hours")] = 1,
    no_cache: Annotated[bool, typer.Option("--no-cache", help="Force re-fetch from GitHub")] = False,
    workers: Annotated[int, typer.Option("--workers", help="Parallel workers (0=auto)")] = 0,
    json_output: Annotated[bool, typer.Option("--json", help="Output in JSON format")] = False,
    interactive: Annotated[bool, typer.Option("--interactive", help="Select and analyze an issue")] = False,
):
    """List and analyze issues in a repository (bulk scan with quick scoring)."""
    from pathlib import Path
    import hashlib
    import subprocess

    repo_dir = Path(repo_path or ".").resolve()

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

    owner, repo = get_github_remote(repo_dir)
    if not owner or not repo:
        console.print("[bold red]Error:[/bold red] Cannot determine GitHub repo. Run in a git repo with remote origin.")
        raise typer.Exit(1)

    cache_dir = None
    if not no_cache:
        from src.analyzer.cache import get_cache_dir, load_issue_cache, save_issue_cache
        cache_dir = get_cache_dir(repo_dir)
        cached = load_issue_cache(repo_dir, owner, repo, state, cache_ttl)
        if cached:
            issues_data = cached["issues"]
            if global_options.verbose:
                console.print(f"[dim]Using cached results from {cached.get('fetched_at', 'unknown')}[/dim]")
        else:
            cached = None
    else:
        cached = None

    if not cached:
        from src.github.client import GitHubClient
        from src.indexer.storage import VectorStore

        if global_options.verbose:
            console.print(f"[cyan]Fetching issues from {owner}/{repo} (state: {state})...[/cyan]")

        client = GitHubClient(token=global_options.api_key)
        try:
            db_path = str(repo_dir / ".oss-index" / "index.lance")
            vector_store = VectorStore(db_path)

            issues = client.get_issues(owner, repo, state=state)

            if global_options.verbose:
                console.print(f"[cyan]Processing {len(issues)} issues in parallel...[/cyan]")

            repo_id = hashlib.sha256(str(repo_dir).encode()).hexdigest()[:16]
            from src.analyzer.bulk_processor import BulkProcessor
            processor = BulkProcessor(db_path, repo_id, max_workers=workers or None)
            issues_data = processor.process_issues(issues, limit=limit)

            if cache_dir:
                save_issue_cache(repo_dir, owner, repo, state, issues_data, cache_ttl)
        finally:
            client.close()

    if filter_difficulty:
        issues_data = [i for i in issues_data if i.get("difficulty") == filter_difficulty]
    if filter_label:
        issues_data = [
            i for i in issues_data
            if any(filter_label.lower() in l.lower() for l in i.get("labels", []))
        ]

    if sort_by == "difficulty":
        issues_data.sort(key=lambda x: (x.get("quick_score", 0.5), x.get("number", 0)))
    elif sort_by == "number":
        issues_data.sort(key=lambda x: x.get("number", 0))
    elif sort_by == "created":
        issues_data.sort(key=lambda x: x.get("number", 0), reverse=True)

    if json_output:
        import json
        console.print(json.dumps(issues_data, indent=2))
        return

    _display_issues_table(issues_data)

    if interactive:
        selected = Prompt.ask("\nEnter issue number to analyze (or press Enter to skip)", default="")
        if selected and selected.isdigit():
            issue_num = int(selected)
            console.print(f"\n[bold]Analyzing issue #{issue_num}...[/bold]")
            # Run analyze logic for this issue
            from src.github.client import GitHubClient
            from src.analyzer.preprocessor import IssuePreprocessor
            from src.analyzer.retriever import HybridRetriever
            from src.analyzer.scorer import HeuristicScorer
            from src.indexer.storage import VectorStore

            db_path = str(repo_dir / ".oss-index" / "index.lance")
            repo_id = hashlib.sha256(str(repo_dir).encode()).hexdigest()[:16]

            client = GitHubClient(token=global_options.api_key)
            try:
                issue = client.get_issue(owner, repo, issue_num)
                comments = client.get_issue_comments(owner, repo, issue_num, issue_author=issue.user_login)
            finally:
                client.close()

            preprocessor = IssuePreprocessor()
            processed = preprocessor.process(issue.title, issue.body)
            processed.comments = _build_issue_comment_contexts(comments)

            retriever = HybridRetriever(db_path=db_path)
            retrieval = retriever.search(processed, repo_id, limit=10)

            from src.analyzer.config import get_ai_config, ProviderName
            from src.analyzer.llm_provider import get_provider_instance
            from src.analyzer.ai_scorer import AIScorer

            ai_config = get_ai_config()
            heuristic_scorer = HeuristicScorer(db_path=db_path)

            use_ai = ai_config.is_configured
            if use_ai:
                provider = get_provider_instance(ai_config.provider)
                if provider:
                    ai_scorer = AIScorer(
                        provider=provider,
                        fallback_scorer=heuristic_scorer,
                        temperature=ai_config.temperature,
                        max_tokens=ai_config.max_tokens,
                        context_unit_budget=ai_config.context_unit_budget,
                    )
                    result = ai_scorer.score(retrieval)
                else:
                    result = heuristic_scorer.score(retrieval)
                    use_ai = False
            else:
                result = heuristic_scorer.score(retrieval)

            _display_analysis_result(result, issue, use_ai)

            # Feedback loop: ask to update cached quick score
            if use_ai and cache_dir:
                from src.analyzer.cache import load_issue_cache, update_cached_issue_difficulty
                quick_score = next((i for i in issues_data if i.get("number") == issue_num), None)
                if quick_score and quick_score.get("difficulty") != result.overall_difficulty.difficulty:
                    console.print(f"\n[yellow]Discrepancy detected![/yellow]")
                    console.print(f"  Quick score: {quick_score['difficulty']} (conf: {quick_score['confidence']:.0%})")
                    console.print(f"  AI score:    {result.overall_difficulty.difficulty} (conf: {result.overall_difficulty.confidence:.0%})")
                    if Confirm.ask("Update cached quick score to match AI?"):
                        update_cached_issue_difficulty(
                            repo_dir, owner, repo, issue_num,
                            result.overall_difficulty.difficulty,
                            result.overall_difficulty.raw_score,
                        )
                        console.print("[green]Cached quick score updated![/green]")


def _display_issues_table(issues_data: list[dict]) -> None:
    """Display issues in a rich table."""
    table = Table(title=f"Issues ({len(issues_data)} found)")
    table.add_column("#", style="cyan", width=6)
    table.add_column("Title", style="white", no_wrap=False)
    table.add_column("Difficulty", style="green", width=10)
    table.add_column("Conf", style="yellow", width=8)
    table.add_column("Labels", style="blue", no_wrap=False)

    difficulty_colors = {"easy": "green", "medium": "yellow", "hard": "red", "unknown": "white"}

    for issue in issues_data:
        diff_color = difficulty_colors.get(issue.get("difficulty"), "white")
        conf = issue.get("confidence", 0.0)
        conf_str = f"{conf:.0%}"
        if conf < 0.6:
            conf_str += " [dim](LOW)[/dim]"

        labels = issue.get("labels", [])
        labels_str = ", ".join(labels[:3])
        if len(labels) > 3:
            labels_str += "..."

        title = issue.get("title", "")
        if len(title) > 50:
            title = title[:47] + "..."

        table.add_row(
            str(issue.get("number", "")),
            title,
            f"[{diff_color}]{issue.get('difficulty', 'unknown').upper()}[/]",
            conf_str,
            labels_str,
        )

    console.print(table)
    console.print("\n[dim]Run 'oss-issue-analyzer analyze <number>' for detailed analysis[/dim]")


def _display_analysis_result(result, issue, use_ai: bool) -> None:
    """Display the analysis result (reused from analyze command)."""
    from src.analyzer.scorer import DifficultyScore
    from rich.panel import Panel

    difficulty_color = {
        "easy": "green",
        "medium": "yellow",
        "hard": "red",
    }.get(result.overall_difficulty.difficulty, "white")

    method_badge = f" [AI]" if use_ai else " [Heuristic]"

    console.print(Panel(
        f"[bold]Difficulty:[/bold] [{difficulty_color}]{result.overall_difficulty.difficulty.upper()}[/] (conf: {result.overall_difficulty.confidence:.0%}){method_badge}" +
        (f"\n[bold]Relative:[/bold] Easier than {result.overall_difficulty.relative_percentile:.0%}"
         if result.overall_difficulty.relative_percentile else ""),
        title=f"Issue: {issue.title[:60]}{'...' if len(issue.title) > 60 else ''}",
        border_style=difficulty_color,
    ))

    _print_analysis_details(result)

    if result.is_good_first_issue:
        console.print("\n[bold green]🎯 This issue is suitable as a good first issue![/bold green]")


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
