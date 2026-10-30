# Project progress: Gravedigger

## Status
- Current day: 2
- Works: add LLM layer (llm.py: prompt, robust parsing, retry-once, fallback, on-disk cache, quality gate, `python -m gravedigger.llm` entry point)
- Broken/open: epitaph quality (a 30-graves run on the previous prompt had about 10 outputs with wrong numbers or last_words contradicting the death); average 14.8s per grave versus the 2.3s measured earlier (cause not yet diagnosed); cache directory did not persist between runs (cause not yet diagnosed)
- Committed: llm.py, test_llm.py, .gitignore (110ef60)
- Stashed: none

## Decisions
- LLM calls use think=False (hybrid reasoning model; thinking is slow and breaks JSON parsing). Strip <think> blocks as a fallback.
- think=False MUST be a top-level kwarg of ollama.chat, never inside options (inside options it is ignored: about 13s versus 2.4s per call); options num_predict=200, temperature=0.7, keep_alive="30m"
- The model must not write numbers (real facts are engraved from data by the HTML page)
- Quality gate rejects digits, number words, banned clichés, survival phrases, copies of the commit message and duplicates
- Failed or fallback results are never cached as LLM results
- Tests mock the client and never touch the real cache dir
- Git log parsed with %x1f separator, COMMIT marker lines; filenames can contain spaces
- Noise filters as module-level constants (extensions, filenames, path prefixes)
- Most recent death per path kept by processing git log newest-first
- Birth found by position in single bulk log (--reverse, name-status with -M), not by date comparison
- Notability = lifespan_days * log1p(lines_at_death) with 1.5x bonus for .py only; log compresses size range so huge files don't dominate
- lines_at_death used (not peak lines) because peak would require reading every revision of every file
- Diversity cap: MAX_PER_DIRECTORY = 3 per top-level directory; top-level files each get own group
- Mass graves: MASS_GRAVE_MIN = 5 deaths in same commit merged before cap; common dir in path
- Backfill: if cap leaves < limit, fill from removed highest-notability first
- Founder bonus: FOUNDER_WINDOW_DAYS = 30, FOUNDER_BONUS = 3.0 (about 3x for files born within 30 days of the root commit); applied in calculate_notability()

## Done log
### Day 1
- Created gravedigger/exhume.py with Death dataclass and find_deaths()
- Implemented noise filtering (extensions, filenames, path prefixes)
- Created tests/test_exhume.py with 8 tests covering all required cases (a-g)
- All tests pass
- Wired debug output into CLI (prints count + first 15 deaths)
- Verified against flask repo: found 207 deaths
- **Audit**: All 4 behaviors verified in code; check_deaths.py run on flask repo — 207 deaths, 0 noise, 0 resurrected in results; breakdown: raw 251 → -1 resurrected → -43 noise → 207; rename detection (-M) makes no difference; counts match exactly; ollama>=0.6 pinned in pyproject.toml
- **Verification pass**: Only README.md is resurrected (deleted 2013→reverted→updated 2024/2025); field check on flask.py, examples/persona/persona.py, src/flask/_compat.py — all 5 fields match git exactly; enrich not yet implemented (Part 2); working tree clean, committed in fd60804
- Implemented Grave dataclass and enrich() with single bulk log for births (HEAD, --reverse, -M, name-status)
- Birth by log position (last A/R before D), not date comparison; -c core.quotepath=off; R lines tab-separated; C ignored
- Binary detection via NUL byte check on bytes before decode
- 7 new tests: (a) plain birth/death/lifespan, (b) second birth after recreate, (c) rename birth, (d) last_snippet correct, (e) binary skipped, (f) older bigger outranks younger smaller, (g) same-timestamp birth/death
- CLI prints top 10 by notability + enrichment time
- Flask repo: 205 graves, 2 skipped, enrichment took 12.06s
- **Part A verification**:
  - src/flask/_compat.py: birth = rename into src/ (ca278a8, 2019-06-01, David Lord) — matches git log --diff-filter=A; correct because the file's current path began at the rename, not the 2010 original add
  - docs/deploying/fastcgi.rst: birth = original add (c64a4e0, 2010-04-19, Armin Ronacher) — matches exactly
  - 205 graves + 2 skipped = 207 deaths ✓
  - Skipped: SiteEgg.egg (binary, NUL byte), docs/_themes (directory, no birth)
  - Committed as b9572cd, pushed to origin/main
- **Part B implemented**:
  - Bonus changed to .py only (1.5x); .rst/.md no bonus
  - Mass graves: MASS_GRAVE_MIN=5, merge before cap, common dir path
  - Diversity cap: MAX_PER_DIRECTORY=3 per top-level dir; top-level files separate groups
  - Backfill to limit after cap
  - exhume(repo, limit=30) full pipeline
  - JSON export in gravedigger/export.py with ISO dates, --json CLI option
  - 7 new tests (mass graves, cap, backfill, JSON roundtrip) — all 24 tests pass
  - Flask repo: 30 graves in 12.49s; top: docs/deploying/fastcgi.rst (24299), docs/ mass grave (23687), scripts/make-release.py (22341)
  - Added graveyard.json to .gitignore

### Day 2
- Created gravedigger/llm.py with Epitaph dataclass, prompt template, robust JSON parsing (handles  blocks, markdown fences, trailing text), retry-once with re-prompt, deterministic fallback epitaph, on-disk cache keyed by (path, death_commit, model), quality gate (rejects digits, number words, banned clichés, survival phrases, commit message copies, duplicates)
- think=False as top-level kwarg (not in options); options: num_predict=200, temperature=0.7, keep_alive="30m"
- Entry point `python -m gravedigger.llm` reads graveyard.json, writes enriched JSON with epitaphs
- Created tests/test_llm.py with 104 tests (prompt, parsing, cache, quality gate, fallback, retry, client mocking) — all pass
- 30-graves flask run: ~14.8s/grave; cache did not persist; about 10/30 had quality issues (invented numbers, contradictory last_words)
- Committed as 110ef60

## Known issues (deliberately deferred)
- flask.py (founding file) ranks 93/205 and is not in the top 30; founder bonus alone was not enough.
- Boilerplate files (LICENSE, AUTHORS, Makefile, tox.ini...) take ~10 slots in the top 30.
- Fix if time: reserve 2 slots for the largest founder .py files; demote boilerplate x0.25. Optional, Day 3 only.

## Next up (Day 2 remainder, in order)
1. numberless prompt + stricter gate + speed diagnosis (check prompt_eval_count/eval_count/thinking) + cache-path fix, one round only
2. HTML graveyard (render.py): single self-contained file, spooky theme plus Noche de Muertos toggle, scattered tombstone scene with click-to-open cards, real stats engraved from data, all repo-derived strings HTML-escaped, prefers-reduced-motion respected
3. CLI wiring: gravedigger <repo> -o graveyard.html with --model, --no-llm, --cache-dir
4. progress file + commit
Day 3: README, dev.to post, optional ranking fix (flask.py missing from the top 30, boilerplate demotion)

## Story notes (for the dev.to post)
- README.md: the phoenix file — deleted in 2013 (revert "update to markdown"), brought back, rewritten in 2024, SVG logos added in 2025. Died 5+ times, always resurrected. The only file find_deaths correctly excludes as resurrected.
- The coding agent thrashed on a regex creating many scratch files
- The agent's tool layer mangled the literal thinking tag (placeholders like "hello" and an XML prefix appeared), fixed by building the tag from chr(60)/chr(62)
- think=False inside options was silently ignored (about 5x slowdown)
- The 2B model invented numbers (for example 135,000 days for a LICENSE) so the design moved to model-writes-the-joke, code-engraves-the-facts
(Moments worth writing about: a tombstone that moved you, a funny epitaph,
a model failure, something you learned.)