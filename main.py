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
):
    pass


@app.command()
def config(
    action: Annotated[str, typer.Argument(help="Action to perform (set, get, list)")],
    key: Optional[str] = None,
    value: Optional[str] = None,
):
    pass


if __name__ == "__main__":
    app()
