"""Command-line entry point for Gravedigger."""
import time
from pathlib import Path

import click

from gravedigger.exhume import exhume
from gravedigger.export import graves_to_json
from gravedigger.llm import enrich_graves_with_llm, _get_model_name
from gravedigger.render import render_html, load_graves_from_json, GraveData


@click.command()
@click.argument("repo_path", type=click.Path(exists=True, file_okay=False))
@click.option("-o", "--output", default="graveyard.html", help="Output HTML file.")
@click.option("--json", "json_path", type=click.Path(), help="Write graves as JSON to this file.")
@click.option("--limit", default=30, help="Number of graves to return.")
@click.option("--model", help="Ollama model name (default: GRAVEDIGGER_MODEL env or qwen3.5:2b)")
@click.option("--no-llm", is_flag=True, help="Skip LLM, use fallback epitaphs only.")
@click.option("--cache-dir", type=click.Path(file_okay=False), help="Cache directory for LLM results.")
def main(repo_path: str, output: str, json_path: str | None, limit: int,
         model: str | None, no_llm: bool, cache_dir: str | None) -> None:
    """Dig up the files your repo buried and render a graveyard."""
    repo = Path(repo_path)

    # Set cache directory if provided
    if cache_dir:
        import os
        os.environ["GRAVEDIGGER_CACHE_DIR"] = cache_dir

    click.echo(f"Exhuming graves from {repo}...")
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

    # Enrich with epitaphs
    if no_llm:
        click.echo("Using fallback epitaphs (--no-llm)...")
        # Create a mock model that will fail and trigger fallback
        model_name = "none"
    else:
        model_name = _get_model_name(model)
        click.echo(f"Generating epitaphs with model: {model_name}...")

    enrich_start = time.perf_counter()
    enriched = enrich_graves_with_llm(graves, model=None if no_llm else model)
    enrich_elapsed = time.perf_counter() - enrich_start

    llm_count = sum(1 for g in enriched if g.source == "llm")
    fallback_count = sum(1 for g in enriched if g.source == "fallback")
    click.echo(f"Enriched {len(enriched)} graves in {enrich_elapsed:.2f}s (llm={llm_count}, fallback={fallback_count})")

    # Convert to GraveData for rendering
    grave_data = []
    for g in enriched:
        grave_data.append(GraveData(
            path=g.path,
            death_commit=g.death_commit,
            death_date=g.death_date,
            killer=g.killer,
            death_message=g.death_message,
            born_commit=g.born_commit,
            born_date=g.born_date,
            born_message=g.born_message,
            born_by=g.born_by,
            lifespan_days=g.lifespan_days,
            lines_at_death=g.lines_at_death,
            last_snippet=g.last_snippet,
            notability=g.notability,
            members=g.members,
            is_mass=g.is_mass,
            epitaph=g.epitaph,
            last_words=g.last_words,
            source=g.source,
        ))

    # Render HTML
    click.echo(f"Rendering HTML to {output}...")
    render_start = time.perf_counter()
    html_output = render_html(grave_data)
    Path(output).write_text(html_output, encoding="utf-8")
    render_elapsed = time.perf_counter() - render_start

    click.echo(f"Rendered in {render_elapsed:.2f}s")
    click.echo(f"Total time: {elapsed + enrich_elapsed + render_elapsed:.2f}s")
    click.echo(f"Open {output} in a browser to view the graveyard.")


if __name__ == "__main__":
    main()