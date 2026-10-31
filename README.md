<div align="center">

# 🪦 Gravedigger

### Where deleted files rest in peace.

Turn any git repository's deleted files into a haunted, offline **tombstone graveyard**, with epitaphs written by a small local AI.

![Python](https://img.shields.io/badge/python-3.13-blue)
![Ollama](https://img.shields.io/badge/LLM-Ollama%20(local)-black)
![Offline](https://img.shields.io/badge/output-offline%20HTML-green)
![Tests](https://img.shields.io/badge/tests-132%20passing-brightgreen)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

<!-- Add a screenshot or GIF here: ![Gravedigger demo](docs/demo.png) -->

</div>

Built for the **Hacktoberfest Open-Source AI Challenge, Week 4: "Ghost in the Machine"**.

---

## Table of Contents

- [The Problem](#the-problem)
- [The Solution](#the-solution)
- [Features](#features)
- [Demo](#demo)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [How It Works](#how-it-works)
- [Design Decisions](#design-decisions)
- [Project Structure](#project-structure)
- [Testing](#testing)
- [Limitations](#limitations)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

---

## The Problem

Every long-lived repository is full of ghosts: files that lived for years, shaped the project, and were then deleted by a single commit. Their story is still in git, but it is nearly impossible to *see*:

- `git log --diff-filter=D` gives you a flat wall of paths and hashes, with no sense of which deletions mattered.
- You can't tell a 13-year-old setup script from a throwaway scratch file.
- Renames, recreated files and mass deletions make the raw log misleading.
- Nobody onboarding to a project reads that history, so the project's past is forgotten.

## The Solution

Gravedigger reads the history for you, works out which deleted files mattered most, and presents them as a **graveyard you can walk through**: one tombstone per notable file, with the real facts engraved on it and a short, darkly funny epitaph.

It is part code-archaeology tool, part toy, and part a case study in using a **small local model safely**: the model writes the joke, and the code engraves the facts.

## Features

- **Fast exhumation.** Finds every deleted file from one bulk `git log` pass, with rename detection and correct handling of filenames with spaces.
- **Noise and resurrection filtering.** Ignores build junk, binaries and files that were deleted but later brought back.
- **Notability ranking.** `lifespan_days × log1p(lines_at_death)`, with a bonus for `.py` files and files born near the first commit.
- **Mass graves.** Five or more files deleted in one commit are merged into a single wide stone.
- **Diversity cap.** At most 3 stones per top-level directory, so one folder can't take over the page.
- **Local AI epitaphs.** Qwen via [Ollama](https://ollama.com), fully offline: no API key, no cost, your history never leaves your machine.
- **Quality gate, retry and fallback.** Bad model output is rejected, retried once, then replaced by a deterministic epitaph.
- **On-disk cache.** Epitaphs are cached per (path, death commit, model), so re-runs are near-instant.
- **One self-contained HTML file.** No CDN, no external requests, works offline.
- **Two themes.** A spooky moonlit graveyard and a **Noche de Muertos** theme (toggle in the corner, remembered between visits).
- **Safe and accessible.** All repo-derived text is HTML-escaped, tombstones are real buttons, Esc closes cards, and `prefers-reduced-motion` is respected.

## Demo

The demo graveyard is built from [pallets/flask](https://github.com/pallets/flask) (5,562 commits):

| | |
|---|---|
| Deaths found | 207 |
| Enriched graves | 205 (2 skipped: a binary file and a directory) |
| Stones shown | 30 |
| Lines buried | 4,910 |
| Longest life | 13 years |
| Deadliest year | 2019 |

Clicking a stone opens a card with the epitaph, last words, and engraved facts: born, died, lifespan, lines at death, the killing commit and author, and the last snippet the file ever held. For example:

> **`docs/deploying/fastcgi.rst`**: *"FastCGI deployment guide deleted mid-explanation."*
> Last words: *"Still trying to convince me it's worth reading."*

> **`LICENSE`**, last words: *"Did not expect the end to be so brief."*

<!-- Optional: link a live demo (GitHub Pages) and the DEV post / video here. -->

## Quick Start

**Requirements**

- Python 3.13 (developed and tested on it)
- `git`
- [Ollama](https://ollama.com) with a model pulled: `ollama pull qwen3.5:2b` *(not needed with `--no-llm`)*

**Install**

```bash
git clone <this-repo-url>
cd gravedigger
python -m venv .venv
# Windows PowerShell:  .\.venv\Scripts\Activate.ps1
# Linux / macOS:       source .venv/bin/activate
pip install -e .
```

**Run it on any local git repository**

```bash
gravedigger path/to/repo -o graveyard.html --limit 30
```

Open `graveyard.html` in a browser.

> **Tip:** load the model once before the first run so the first grave isn't slow:
> `ollama run qwen3.5:2b "hi"`, then `/bye`. The CLI is quiet while it generates, so expect about 1-2 minutes on the first uncached run. Later runs use the cache.

**No Ollama? No problem.**

```bash
gravedigger path/to/repo -o graveyard.html --no-llm
```

This uses deterministic fallback epitaphs and takes about 10 seconds on a repo the size of Flask.

## Usage

```
gravedigger <repo> [options]
```

| Option | Description | Default |
|---|---|---|
| `-o, --output FILE` | Output HTML file | `graveyard.html` |
| `--limit N` | Number of graves to show | `30` |
| `--model NAME` | Ollama model for epitaphs | `qwen3.5:2b` |
| `--no-llm` | Skip the model, use fallback epitaphs | off |
| `--cache-dir DIR` | Where epitaphs are cached | `~/.gravedigger_cache` |
| `--json` | Also export the graves as JSON | off |

**Two-step workflow** (useful for inspecting or hand-editing epitaphs):

```bash
# 1. export graves to JSON (via --json), then add epitaphs
python -m gravedigger.llm graveyard.json -o epitaphs.json --limit 30
```

`epitaphs.json` holds each grave with its generated epitaph and last words.

## How It Works

```
 git history ──► exhume ──► enrich ──► rank & group ──► epitaphs ──► render
 (one bulk log)  deaths     births,     notability,      local LLM    one HTML
                 + filters  lines,      mass graves,     + gate,      file
                            snippet     diversity cap    cache
```

1. **Exhume** (`exhume.py`): parses the git log (newest first, `%x1f`-separated fields, `COMMIT` marker lines) and keeps the most recent death per path. Noise filters (extensions, filenames, path prefixes) are module-level constants. Files that were later resurrected are excluded.
2. **Enrich**: finds each file's *birth* by its position in a single bulk `--reverse` log with rename detection (not by comparing dates), then reads lines and the last snippet at death. Binary files are skipped (NUL-byte check).
3. **Rank and group**: scores notability, merges mass graves, applies the per-directory cap, then backfills from the highest-scored removed graves if the cap leaves too few.
4. **Epitaphs** (`llm.py`): builds a numberless prompt, calls the local model, parses the JSON robustly (handles fences, trailing text and stray `<think>` blocks), applies the quality gate, retries once, falls back if needed, and caches good results.
5. **Render** (`render.py`): produces one self-contained HTML file with a scattered tombstone scene, click-to-open cards, header stats computed from data, and both themes.

## Design Decisions

- **The model writes jokes; code engraves facts.** An early run let a 2B model write whole epitaphs. Roughly a third of the outputs had invented numbers or last words that contradicted the death (one LICENSE "lived 135,000 days"). The model is now forbidden from writing digits, and every date, lifespan and line count is engraved from git data.
- **Quality gate.** Rejects digits, number words, banned clichés, survival phrases, copies of the commit message, duplicates, over-long text and foreign file paths. Failed or fallback results are never cached as LLM output.
- **`think=False` is a top-level argument of `ollama.chat`.** Inside `options` it is silently ignored and every call was about 5x slower (about 13s versus 2.4s).
- **Birth by log position.** Handles renames and recreated files correctly, unlike date comparison.
- **`lines_at_death`, not peak size.** Peak would require reading every revision of every file.
- **Log-scaled size.** A huge file can't drown out a long-lived small one.
- **Escape everything.** Paths, commit messages, authors, snippets and epitaphs are all HTML-escaped, with a test using a path containing `<script>`.

## Project Structure

```
gravedigger/
├── gravedigger/
│   ├── exhume.py    # deaths, births, notability, mass graves, diversity cap
│   ├── llm.py       # prompt, parsing, quality gate, cache, fallback
│   ├── render.py    # self-contained HTML graveyard
│   ├── export.py    # JSON export
│   └── cli.py       # `gravedigger` command
├── tests/           # exhume, llm and render tests
├── AGENTS.md        # rules for the coding agent
├── project_progress.md
└── pyproject.toml
```

## Testing

```bash
python -m pytest -q
```

132 tests. The Ollama client is mocked and the real cache directory is never touched.

## Limitations

- Ranking is a heuristic. Boilerplate files (LICENSE, AUTHORS, `tox.ini`) take several slots, and Flask's founding `flask.py` ranks just below the cut.
- A 2B model writes uneven epitaphs: some are sharp, many are flat. The engraved facts carry the page.
- Files deleted and later restored are excluded by design.
- Tested mainly on Windows with the Flask repository.

## Roadmap

- [ ] Reserve slots for the largest founder `.py` files
- [ ] Demote boilerplate files (LICENSE, AUTHORS, config) in the ranking
- [ ] Progress output during epitaph generation
- [ ] `--epitaphs FILE` to render from a hand-edited epitaph file
- [ ] Optional GitHub Pages deploy of the generated graveyard

## Contributing

Issues and pull requests are welcome. To get started:

```bash
pip install -e .
python -m pytest -q
```

Please keep the tests passing and add a test for new behaviour. Never type literal HTML entities in tests; compare against `html.escape()` instead.

## License

MIT. Add a `LICENSE` file to the repository root with the MIT text.

## Acknowledgments

- [pallets/flask](https://github.com/pallets/flask) for the demo history
- [Ollama](https://ollama.com) and the Qwen team for the local model
- Hacktoberfest and DEV for the "Ghost in the Machine" challenge
- Built with coding agents: Nemotron 3 Ultra via OpenCode, planned with Claude