"""Installable assignment CLI. Errors are sanitized; no live calls unless selected."""

import json
from pathlib import Path

import typer
from dotenv import load_dotenv

from covenants.evaluation import compare as run_comparison
from covenants.evaluation import evaluate, write_eval
from covenants.extraction import extract as extract_agreement
from covenants.providers import ProviderError, get_provider

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)


@app.command()
def extract(agreement: Path, provider: str = "fake", out: Path = Path("out/extraction.json")):
    """Extract covenants from a text/Markdown agreement."""
    load_dotenv(override=False)
    try:
        result = extract_agreement(agreement.read_text(), get_provider(provider))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(result.model_dump_json(indent=2) + "\n")
        typer.echo(f"{result.agreement_id}: {len(result.covenants)} covenants -> {out}")
    except (OSError, ValueError, ProviderError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from None


@app.command("eval")
def eval_command(provider: str = "fake"):
    """Evaluate one provider against the committed expected answers."""
    load_dotenv(override=False)
    try:
        report = evaluate(get_provider(provider))
        write_eval(report, Path("reports"))
        typer.echo(json.dumps(report, indent=2))
    except (OSError, ValueError, ProviderError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from None


@app.command("compare")
def compare_command(providers: str = typer.Option(..., "--providers"), record: bool = False):
    """Compare comma-separated providers; optionally record responses for offline replay."""
    load_dotenv(override=False)
    try:
        reports = run_comparison([n.strip() for n in providers.split(",") if n.strip()], record=record)
        typer.echo(json.dumps(reports, indent=2))
        typer.echo("Wrote reports/comparison.md")
    except (OSError, ValueError, ProviderError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from None


if __name__ == "__main__":
    app()

