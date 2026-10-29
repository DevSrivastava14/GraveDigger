"""Command-line entry point for Gravedigger."""
import click
import time
from pathlib import Path

from gravedigger.exhume import find_deaths, enrich


@click.command()
@click.argument("repo_path", type=click.Path(exists=True, file_okay=False))
@click.option("-o", "--output", default="graveyard.html", help="Output HTML file.")
def main(repo_path: str, output: str) -> None:
    """Dig up the files your repo buried."""
    repo = Path(repo_path)
    deaths = find_deaths(repo)
    click.echo(f"Found {len(deaths)} deaths")

    start = time.perf_counter()
    graves, skipped = enrich(repo, deaths)
    elapsed = time.perf_counter() - start

    click.echo(f"Enriched into {len(graves)} graves ({skipped} skipped) in {elapsed:.2f}s")
    click.echo("Top 10 by notability:")
    for g in graves[:10]:
        click.echo(f"  {g.notability:.1f}  {g.lifespan_days}d  {g.lines_at_death} lines  {g.path}")
    click.echo(f"Output would go to {output} (not implemented yet)")


if __name__ == "__main__":
    main()