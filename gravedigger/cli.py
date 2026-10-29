"""Command-line entry point for Gravedigger."""
import click
from pathlib import Path

from gravedigger.exhume import find_deaths


@click.command()
@click.argument("repo_path", type=click.Path(exists=True, file_okay=False))
@click.option("-o", "--output", default="graveyard.html", help="Output HTML file.")
def main(repo_path: str, output: str) -> None:
    """Dig up the files your repo buried."""
    repo = Path(repo_path)
    deaths = find_deaths(repo)
    click.echo(f"Found {len(deaths)} deaths")
    for d in deaths[:15]:
        click.echo(f"{d.death_date.isoformat()}  {d.path}  {d.death_message}")
    click.echo(f"Output would go to {output} (not implemented yet)")


if __name__ == "__main__":
    main()