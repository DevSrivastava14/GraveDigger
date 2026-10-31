Gravedigger

Where deleted files rest in peace.

Gravedigger digs through a git repository's history, finds every file that was deleted, and turns the most notable ones into a tombstone graveyard: a single, self-contained HTML page. A small local LLM (Qwen via Ollama) writes each epitaph. Every number on the page is engraved from real git data, never written by the model.

Built for the Hacktoberfest Open-Source AI Challenge, Week 4: Ghost in the Machine.

What it does
Exhumes deleted files from git log (one bulk pass, rename-aware).
Filters noise (lockfiles, build artifacts, binaries) and files that were later resurrected.
Ranks the dead by notability: lifespan_days * log1p(lines_at_death), with a bonus for .py files and for files born near the first commit.
Groups mass graves (5+ files deleted in one commit) and caps each top-level directory so one folder can't crowd the page.
Writes epitaphs with a local model (qwen3.5:2b by default), guarded by a quality gate and an on-disk cache.
Renders one offline HTML file: scattered tombstones, click-to-open cards, a spooky night theme and a Noche de Muertos theme.
Quick start

Requirements: Python 3.10+, git, and Ollama with a model pulled (ollama pull qwen3.5:2b). Ollama is not needed with --no-llm.

powershell
git clone <this-repo-url>
cd gravedigger
python -m venv .venv
.\.venv\Scripts\Activate.ps1      # Linux/macOS: source .venv/bin/activate
pip install -e .

Run it on any local git repository:

powershell
# Full run, with LLM epitaphs
gravedigger path\to\repo -o graveyard.html --limit 30

# No model needed: deterministic fallback epitaphs
gravedigger path\to\repo -o graveyard.html --no-llm

Then open graveyard.html in a browser. It works offline and has no external requests.

Options
Option	Meaning
-o, --output	Output HTML file
--limit N	Number of graves to show (default 30)
--model NAME	Ollama model for epitaphs (default qwen3.5:2b)
--no-llm	Skip the model, use fallback epitaphs
--cache-dir DIR	Epitaph cache (default ~/.gravedigger_cache)
--json	Also export the graves as JSON

Tip: load the model once before the first run (ollama run qwen3.5:2b "hi", then /bye) so the first grave isn't slow. Epitaphs are cached per (path, death commit, model), so later runs are near-instant.

Design decisions
The model writes jokes, code writes facts. An early 2B-model run invented numbers (for example, a LICENSE that "lived 135,000 days"). The model is now forbidden from writing digits. Dates, lifespans, line counts and the killing commit are engraved from git data by the page.
Quality gate. Epitaphs containing digits, number words, clichés, survival phrases, copies of the commit message, duplicates, over-long text or foreign file paths are rejected, retried once, then replaced by a deterministic fallback. Fallbacks are never cached as LLM output.
think=False must be a top-level argument of ollama.chat. Inside options it is silently ignored, and every call was about 5x slower (about 13s versus 2.4s).
Birth by log position, not by date comparison, so renames and recreated files are handled correctly.
Safe rendering. Every repo-derived string (paths, commit messages, authors, snippets, epitaphs) is HTML-escaped, and there is a test for a path containing <script>.
Accessible. Tombstones are real buttons, Esc closes cards, and prefers-reduced-motion is respected.
Demo repository

The demo graveyard is built from pallets/flask (5,562 commits): 207 deaths found, 205 enriched, the 30 most notable shown.

Tests
powershell
python -m pytest -q

The suite mocks the Ollama client and never touches the real cache directory.

Project layout
gravedigger/
  exhume.py   # find deaths, births, notability, mass graves, diversity cap
  llm.py      # prompt, parsing, quality gate, cache, fallback
  render.py   # self-contained HTML graveyard
  export.py   # JSON export
  cli.py      # gravedigger command
tests/
Known limitations
Ranking is a heuristic: boilerplate files (LICENSE, AUTHORS, tox.ini) take several slots, and the founding flask.py ranks below the cut.
A 2B model writes uneven epitaphs. Some are sharp, many are flat. The engraved facts carry the page.
Files that were deleted and later brought back are excluded by design.
License

MIT (add a LICENSE file if you haven't yet).