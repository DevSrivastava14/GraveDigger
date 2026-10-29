"""Command-line entry point for Gravedigger."""
import click
import time
from pathlib import Path

from gravedigger.exhume import exhume
from gravedigger.export import graves_to_json


@click.command()
@click.argument("repo_path", type=click.Path(exists=True, file_okay=False))
@click.option("-o", "--output", default="graveyard.html", help="Output HTML file.")
@click.option("--json", "json_path", type=click.Path(), help="Write graves as JSON to this file.")
@click.option("--limit", default=30, help="Number of graves to return.")
def main(repo_path: str, output: str, json_path: str | None, limit: int) -> None:
    """Dig up the files your repo buried."""
    repo = Path(repo_path)

    start = time.perf_counter()
    graves = exhume(repo, limit=limit)
    elapsed = time.perf_counter() - start

    click.echo(f"Exhumed {len(graves)} graves in {elapsed:.2f}s")
    click.echo("Top graves by notability:")
    for i, g in enumerate(graves, 1):
        mass_flag = " [MASS]" if g.is_mass else ""
        click.echo(f"  {i:2d}. {g.notability:.1f}  {g.lifespan_days}d  {g.lines_at_death} lines  {g.path}{mass_flag}")

    if json_path:
        json_str = graves_to_json(graves)
        Path(json_path).write_text(json_str, encoding="utf-8")
        click.echo(f"Wrote JSON to {json_path}")

    click.echo(f"HTML output would go to {output} (not implemented yet)")


if __name__ == "__main__":
    main()