"""Command-line entry point for Gravedigger."""
import click


@click.command()
@click.argument("repo_path", type=click.Path(exists=True, file_okay=False))
@click.option("-o", "--output", default="graveyard.html", help="Output HTML file.")
def main(repo_path: str, output: str) -> None:
    """Dig up the files your repo buried."""
    click.echo(f"Digging in {repo_path} ... (not implemented yet)")