import typer
from rich.console import Console

app = typer.Typer()
console = Console()


@app.command()
def start():
    console.print("[bold green]Welcome to OSS Issue Analyzer![/bold green]")
    console.print("Application started successfully.")


if __name__ == "__main__":
    app()
